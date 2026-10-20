"""Read-only tracker discovery; never creates or modifies Notion records."""
import argparse
import json
import os
import sys
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

API = 'https://api.notion.com/v1'
VERSION = '2025-09-03'
TRACKER = '3ee90d2e-cd48-83ff-9bf8-018a18a29562'


class InspectionError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise InspectionError('Unexpected API redirect refused to protect authentication.')


class NotionReader:
    def __init__(self):
        self.token = os.environ.get('NOTION_TOKEN')
        if not self.token:
            raise InspectionError('NOTION_TOKEN is missing. Enter it securely in environment settings and share the tracker with the Notion connection.')
        self.opener = build_opener(NoRedirect())

    def request(self, path, body=None):
        # Fixed API host; path is formed exclusively by this inspection tool.
        for attempt in range(4):
            req = Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                          headers={'Authorization': 'Bearer ' + self.token, 'Notion-Version': VERSION, 'Content-Type': 'application/json'})
            try:
                with self.opener.open(req, timeout=30) as response:
                    return json.load(response)
            except HTTPError as exc:
                if (exc.code == 429 or exc.code in (502, 503, 504)) and attempt < 3:
                    retry = exc.headers.get('Retry-After', '')
                    time.sleep(min(int(retry), 30) if retry.isdigit() else 2 ** attempt)
                    continue
                raise InspectionError(f'Notion HTTP {exc.code}. Check connection access, token binding, and tracker sharing. No records changed.') from exc
            except (URLError, TimeoutError, OSError) as exc:
                raise InspectionError('Notion connection failed. Check network access and TLS trust. No records changed.') from exc
        raise InspectionError('Notion read retries exhausted.')

    def blocks(self, block_id):
        results, cursor = [], None
        while True:
            from urllib.parse import urlencode
            query = urlencode({'page_size': 100, **({'start_cursor': cursor} if cursor else {})})
            response = self.request(f'/blocks/{block_id}/children?{query}')
            results.extend(response['results'])
            if not response.get('has_more'):
                return results
            cursor = response['next_cursor']

    def sample(self, source_id):
        # POST is Notion's read-only query method, never a write.
        return self.request(f'/data_sources/{source_id}/query', {'page_size': 5})

    def inspect(self):
        page = self.request(f'/pages/{TRACKER}')
        sources, blocks, visited = [], [], set()

        def visit(block_id, depth=0):
            if block_id in visited:
                return
            if depth > 12 or len(visited) >= 200:
                raise InspectionError('Tracker traversal limit reached; inspection incomplete. Narrow the relevant section manually.')
            visited.add(block_id)
            for block in self.blocks(block_id):
                blocks.append(block)
                if block['type'] == 'child_database':
                    database = self.request('/databases/' + block['id'])
                    for source in database.get('data_sources', []):
                        schema = self.request('/data_sources/' + source['id'])
                        sources.append({'database': database, 'schema': schema, 'sample': self.sample(source['id'])})
                elif block.get('has_children'):
                    visit(block['id'], depth + 1)
        visit(TRACKER)
        return {'tracker': page, 'blocks': blocks, 'data_sources': sources,
                'mapping_verified': False,
                'limitations': ['Views and linked-database filters may not be exposed by the API.',
                                'Inspect relation targets and Bryant Barrio assignment before enabling writes.',
                                'A five-record sample does not establish uniqueness or ownership.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='Private local JSON report path; do not commit.')
    args = parser.parse_args()
    try:
        report = NotionReader().inspect()
        # Do not overwrite existing reports; contents may contain personal tracker data.
        with open(args.output, 'x', encoding='utf-8', opener=lambda p, flags: os.open(p, flags, 0o600)) as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
        print('Read-only inspection saved. Review schema and assignment evidence locally; no records changed.')
        return 0
    except (InspectionError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
