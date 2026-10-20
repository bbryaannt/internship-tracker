"""Schema-validated Notion intake. Creates new entries by default; --dry-run never writes; never updates existing records."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request

from extract_job import IntakeError, extract_url, normalize_url
from inspect_notion import InspectionError, NotionReader, API, VERSION

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[2]
MAPPING = SKILL / 'references/notion_mapping.json'


def text(property_value):
    return ''.join(part.get('plain_text', part.get('text', {}).get('content', ''))
                   for part in property_value.get(property_value.get('type'), []))


def key(value):
    return re.sub(r'\W+', ' ', str(value).casefold()).strip()


def rich(value):
    value = str(value)
    return [{'type': 'text', 'text': {'content': value[i:i+1800]}} for i in range(0, len(value), 1800)]


def requisition(job):
    identifier = job.get('source_fields', {}).get('identifier')
    if isinstance(identifier, dict):
        identifier = identifier.get('value')
    if isinstance(identifier, (str, int)) and str(identifier).strip():
        return str(identifier).strip()
    return None


def known_id(value):
    return value.strip() if key(value) not in ('', 'n a', 'na', 'none', 'unknown') else None


def duplicate(job, pages):
    matches, ambiguous = [], []
    for page in pages:
        p = page['properties']
        same_url = bool(p.get('Application Link', {}).get('url')) and normalize_url(p['Application Link']['url']) == normalize_url(job['original_url'])
        company = key(text(p.get('Company', {}))) == key(job['company'])
        title = key(text(p.get('Position', {}))) == key(job['title'])
        old_id = known_id(text(p.get('Application ID', {})))
        new_id = requisition(job)
        # URL identity remains authoritative if a job's metadata changed.
        if same_url or (company and old_id and new_id and key(old_id) == key(new_id)):
            matches.append(page)
        elif company and title:
            if old_id and new_id and key(old_id) != key(new_id):
                continue
            # Without matching IDs/URL, location/season distinctions need review.
            ambiguous.append(page)
    if len(matches) == 1:
        return 'already_tracked', matches
    if matches or ambiguous:
        return 'ambiguous_duplicate', matches + ambiguous
    return 'new', []


class Client(NotionReader):
    def validate(self, mapping):
        schema = self.request('/data_sources/' + mapping['data_source_id'])
        if schema.get('archived') or schema.get('in_trash'):
            raise IntakeError('Destination is archived; writes blocked.')
        if schema.get('parent', {}).get('database_id') != mapping['database_id']:
            raise IntakeError('Destination database changed; inspect mapping again.')
        props = schema['properties']
        for name, expected in mapping['properties'].items():
            actual = props.get(name, {})
            if actual.get('id') != expected['id'] or actual.get('type') != expected['type']:
                raise IntakeError(f'Notion schema changed for {name}; inspect mapping again.')
        options = props['Application Status']['status']['options']
        if not any(o['id'] == mapping['status_option_id'] and o['name'] == mapping['status_option_name'] for o in options):
            raise IntakeError('Not applied option changed; writes blocked.')
        relation = props['Person']['relation']
        if relation.get('data_source_id') != mapping['owner_source_id']:
            raise IntakeError('Person relation destination changed; writes blocked.')
        owner = self.request('/pages/' + mapping['owner_page_id'])
        if owner.get('archived') or owner.get('in_trash') or text(owner['properties']['Name']) != mapping['owner_title']:
            raise IntakeError('Bryant relation target changed; writes blocked.')
        if owner.get('parent', {}).get('data_source_id') != mapping['owner_source_id']:
            raise IntakeError('Bryant relation target is in an unexpected source.')

    def pages(self, mapping):
        pages, cursor = [], None
        while True:
            response = self.request('/data_sources/' + mapping['data_source_id'] + '/query',
                                    {'page_size': 100, **({'start_cursor': cursor} if cursor else {})})
            pages.extend(response['results'])
            if not response.get('has_more'):
                return pages
            cursor = response['next_cursor']

    def create_once(self, payload):
        req = Request(API + '/pages', data=json.dumps(payload).encode(),
                      headers={'Authorization': 'Bearer ' + self.token, 'Notion-Version': VERSION, 'Content-Type': 'application/json'})
        # Never retry page creation automatically: response loss can hide a successful write.
        try:
            with self.opener.open(req, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            raise IntakeError(f'Create returned HTTP {exc.code}; no automatic retry. Reconcile before another creation attempt.') from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise IntakeError('Create outcome is uncertain. Reconcile Notion before retrying; success has not been verified.') from exc


def payload(job, mapping):
    if not all(isinstance(job.get(k), str) and job[k].strip() for k in ('company', 'title', 'description', 'original_url')):
        raise IntakeError('Verified company, title, description and original URL are required.')
    if len(job['title']) > 1800 or len(job['company']) > 1800:
        raise IntakeError('Title or company exceeds the supported length.')
    if job.get('inferred_fields'):
        raise IntakeError('Remove unverified inferred fields before mapping.')
    source = job.get('source_fields', {})
    notes = []
    if job.get('locations'):
        notes.append('Locations: ' + '; '.join(', '.join(str(v) for v in location.values()) for location in job['locations']))
    for k, v in source.items():
        if k == 'identifier':
            continue
        display = '; '.join(v) if isinstance(v, list) and all(isinstance(x, str) for x in v) else v
        notes.append(k.replace('_', ' ').capitalize() + ': ' + (display if isinstance(display, str) else json.dumps(display, ensure_ascii=False)))
    note_text = '\n'.join(notes)
    if len(note_text) > 10_000:
        raise IntakeError('Supplementary metadata is too large; review before creating.')
    props = {'Position': {'title': rich(job['title'])}, 'Company': {'rich_text': rich(job['company'])},
             'Application Link': {'url': job['original_url']},
             'Application Status': {'status': {'id': mapping['status_option_id']}},
             'Person': {'relation': [{'id': mapping['owner_page_id']}]}, 'Notes': {'rich_text': rich(note_text)}}
    if requisition(job):
        if len(requisition(job)) > 1800:
            raise IntakeError('Job identifier exceeds supported length.')
        props['Application ID'] = {'rich_text': rich(requisition(job))}
    description = job['description']
    if len(description) > 90_000:
        raise IntakeError('Description is too large; review rather than silently truncating it.')
    paragraphs = ['Source: ' + job['original_url'], 'Verified posting description:'] + [description[i:i+1800] for i in range(0, len(description), 1800)]
    blocks = [{'object': 'block', 'type': 'paragraph', 'paragraph': {'rich_text': rich(p)}} for p in paragraphs]
    return {'parent': {'type': 'data_source_id', 'data_source_id': mapping['data_source_id']}, 'properties': props, 'children': blocks}


def verify(page, expected, mapping):
    if page.get('archived') or page.get('in_trash') or page.get('parent', {}).get('data_source_id') != mapping['data_source_id']:
        raise IntakeError('Read-back destination verification failed.')
    for name, value in expected['properties'].items():
        actual = page['properties'].get(name, {})
        if 'status' in value:
            good = actual.get('status', {}).get('id') == value['status']['id']
        elif 'relation' in value:
            good = not actual.get('has_more') and {x['id'] for x in actual.get('relation', [])} == {x['id'] for x in value['relation']}
        elif 'url' in value:
            good = actual.get('url') == value['url']
        else:
            field = next(iter(value))
            good = text(actual) == ''.join(x['text']['content'] for x in value[field])
        if not good:
            raise IntakeError(f'Read-back verification failed for {name}. Record may exist; do not create another.')
    if not page.get('url'):
        raise IntakeError('Created page has no verified Notion URL.')


def process(client, mapping, job, create=False, approved=False, state_dir=None):
    expected = payload(job, mapping)
    state, matches = duplicate(job, client.pages(mapping))
    if state != 'new':
        return {'result': state, 'company': job['company'], 'title': job['title'],
                'entries': [{'id': p['id'], 'url': p.get('url')} for p in matches], 'changes_made': False}
    preview = {'result': 'dry_run', 'company': job['company'], 'title': job['title'],
               'assignee': 'Bryant Barrio', 'assignment': {'property': 'Person', 'type': 'relation', 'page_id': mapping['owner_page_id']},
               'status': mapping['status_option_name'], 'destination': mapping['data_source_id'],
               'original_url': job['original_url'], 'proposed_entry': expected}
    digest = hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()
    preview['preview_sha256'] = digest
    if not create:
        return preview
    if not mapping['first_live_verified'] and not approved:
        raise IntakeError('First live entry requires explicit user approval of its dry-run preview.')
    # All callers must use the CLI's local lock; Notion offers no atomic uniqueness key.
    # A second query narrows races, but cross-machine concurrent writers must be serialized.
    state, matches = duplicate(job, client.pages(mapping))
    if state != 'new':
        return {'result': state, 'entries': [{'id': p['id'], 'url': p.get('url')} for p in matches], 'changes_made': False}
    journal = state_dir / (hashlib.sha256(normalize_url(job['original_url']).encode()).hexdigest() + '.json')
    if journal.exists():
        raise IntakeError('A previous creation attempt needs reconciliation; no retry issued. Check the private journal and Notion.')
    with open(journal, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as handle:
        json.dump({'state': 'pending', 'source_url': job['original_url'], 'preview_sha256': digest}, handle)
    created = client.create_once(expected)
    # Persist the page ID immediately so a later failed verification can be recovered.
    journal.write_text(json.dumps({'state': 'created_unverified', 'page_id': created['id'], 'preview_sha256': digest}))
    readback = client.request('/pages/' + created['id'])
    verify(readback, expected, mapping)
    body = client.blocks(created['id'])
    paragraphs = [b.get('paragraph', {}).get('rich_text', []) for b in body if b['type'] == 'paragraph']
    if [''.join(t.get('plain_text', t.get('text', {}).get('content', '')) for t in p) for p in paragraphs] != [''.join(t['text']['content'] for t in b['paragraph']['rich_text']) for b in expected['children']]:
        raise IntakeError('Created entry body verification failed; do not retry creation.')
    journal.write_text(json.dumps({'state': 'verified', 'page_id': readback['id'], 'preview_sha256': digest}))
    return {'result': 'added', 'company': job['company'], 'title': job['title'], 'url': readback['url'],
            'assignee': 'Bryant Barrio', 'status': mapping['status_option_name'], 'verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('urls', nargs='+')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--create', dest='create', action='store_true', help='Add new entries (default; retained for compatibility).')
    mode.add_argument('--dry-run', dest='create', action='store_false', help='Check duplicates and preview only; never create records.')
    parser.set_defaults(create=True)
    parser.add_argument('--approved-preview-sha256', help='Only after explicit approval: exact hash from the first dry-run preview.')
    args = parser.parse_args()
    if args.approved_preview_sha256 and len(args.urls) != 1:
        parser.error('First-live approval applies to exactly one posting.')
    mapping = json.loads(MAPPING.read_text())
    state_dir = ROOT / '.local/intake-journal'
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    results = []
    try:
        client = Client()
        client.validate(mapping)
    except (InspectionError, IntakeError) as exc:
        print(json.dumps({'result': 'blocked', 'reason': str(exc)}))
        return 1
    with open(state_dir / 'intake.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for url in args.urls:
            try:
                job = extract_url(url)
                expected = payload(job, mapping)
                digest = hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()
                if args.approved_preview_sha256 and digest != args.approved_preview_sha256:
                    raise IntakeError('Posting or payload changed since preview; request approval for the new preview.')
                results.append(process(client, mapping, job, args.create, bool(args.approved_preview_sha256), state_dir))
            except (InspectionError, IntakeError, ValueError, OSError, KeyError) as exc:
                results.append({'result': 'unable_to_add', 'url': url, 'reason': str(exc)})
    print(json.dumps({'results': results}, indent=2, ensure_ascii=False))
    return 1 if any(r['result'] in ('unable_to_add', 'ambiguous_duplicate') for r in results) else 0


if __name__ == '__main__':
    sys.exit(main())
