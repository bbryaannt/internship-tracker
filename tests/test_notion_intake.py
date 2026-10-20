import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.agents/skills/internship-tracker/scripts'))
import add_internship as a
import extract_job as e


def job(identifier='123'):
    return {'company': 'Fixture Co', 'title': 'Engineering Intern', 'description': 'Design and test.',
            'original_url': 'https://job-boards.greenhouse.io/fixture/jobs/123', 'locations': [],
            'source_fields': {'identifier': {'value': identifier}} if identifier else {}, 'inferred_fields': {}}


def page(identifier='123', url='https://example.com/another', company='Fixture Co', title='Engineering Intern'):
    return {'id': 'page1', 'url': 'https://notion.so/page1', 'properties': {
        'Company': {'type': 'rich_text', 'rich_text': [{'plain_text': company}]},
        'Position': {'type': 'title', 'title': [{'plain_text': title}]},
        'Application ID': {'type': 'rich_text', 'rich_text': [{'plain_text': identifier}]},
        'Application Link': {'type': 'url', 'url': url}}}


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.mapping = json.loads(a.MAPPING.read_text())

    def test_company_scoped_identifier_duplicate(self):
        self.assertEqual(a.duplicate(job(), [page()])[0], 'already_tracked')
        self.assertEqual(a.duplicate(job(), [page(company='Another Co')])[0], 'new')

    def test_distinct_job_ids_stay_separate(self):
        self.assertEqual(a.duplicate(job(), [page(identifier='456')])[0], 'new')

    def test_missing_identifiers_and_same_title_are_ambiguous(self):
        self.assertEqual(a.duplicate(job(None), [page(identifier='')])[0], 'ambiguous_duplicate')

    def test_normalized_greenhouse_url_duplicate(self):
        url='https://boards.greenhouse.io/fixture/jobs/123?gh_jid=123&utm_source=foo'
        self.assertEqual(a.duplicate(job(), [page(identifier='', url=url)])[0], 'already_tracked')

    def test_multiple_matches_are_ambiguous(self):
        self.assertEqual(a.duplicate(job(), [page(), page()])[0], 'ambiguous_duplicate')

    def test_preview_maps_actual_types_and_does_not_create(self):
        c=Mock(); c.pages.return_value=[]
        result=a.process(c,self.mapping,job())
        p=result['proposed_entry']['properties']
        self.assertEqual(result['result'],'dry_run')
        self.assertEqual(p['Person']['relation'],[{'id':self.mapping['owner_page_id']}])
        self.assertEqual(p['Application Status']['status']['id'], self.mapping['status_option_id'])
        c.create_once.assert_not_called()

    def test_first_live_gate(self):
        c=Mock(); c.pages.return_value=[]
        with self.assertRaisesRegex(e.IntakeError, 'approval'):
            a.process(c,self.mapping,job(),create=True)
        c.create_once.assert_not_called()

    def test_write_timeout_is_not_retried(self):
        c=Mock(); c.pages.return_value=[]; c.create_once.side_effect=e.IntakeError('uncertain')
        with tempfile.TemporaryDirectory() as d:
            for attempt in range(2):
                with self.assertRaises(e.IntakeError):
                    a.process(c,self.mapping,job(),create=True,approved=True,state_dir=Path(d))
            self.assertEqual(c.create_once.call_count,1)

    def test_duplicate_is_never_modified(self):
        c=Mock(); c.pages.return_value=[page()]
        self.assertEqual(a.process(c,self.mapping,job(),create=True)['result'],'already_tracked')
        c.create_once.assert_not_called()

    def test_reads_all_query_pages(self):
        c=a.Client.__new__(a.Client)
        c.request=Mock(side_effect=[{'results':[page()], 'has_more':True, 'next_cursor':'cursor'},
                                   {'results':[], 'has_more':False}])
        self.assertEqual(len(c.pages(self.mapping)),1)
        self.assertEqual(c.request.call_args_list[1].args[1]['start_cursor'],'cursor')

    def test_readback_detects_wrong_owner_status_and_url(self):
        expected=a.payload(job(),self.mapping)
        props={}
        for name,value in expected['properties'].items():
            kind=next(iter(value)); props[name]={'type':kind,**value}
        saved={'parent':{'data_source_id':self.mapping['data_source_id']},'properties':props,'url':'https://notion.so/test'}
        a.verify(saved,expected,self.mapping)
        for name,replacement in [('Person',{'relation':[]}), ('Application Status',{'status':{'id':'wrong'}}), ('Application Link',{'url':'https://wrong.example'})]:
            copy=json.loads(json.dumps(saved));copy['properties'][name]=replacement
            with self.subTest(name=name), self.assertRaises(e.IntakeError):
                a.verify(copy,expected,self.mapping)

    def test_success_requires_body_and_property_readback(self):
        expected=a.payload(job(),self.mapping)
        props={name:{'type':next(iter(value)),**value} for name,value in expected['properties'].items()}
        saved={'id':'new', 'parent':{'data_source_id':self.mapping['data_source_id']}, 'properties':props,'url':'https://notion.so/new'}
        c=Mock();c.pages.return_value=[];c.create_once.return_value={'id':'new'};c.request.return_value=saved
        c.blocks.return_value=expected['children']
        with tempfile.TemporaryDirectory() as d:
            result=a.process(c,self.mapping,job(),create=True,approved=True,state_dir=Path(d))
        self.assertTrue(result['verified'])
        c.request.assert_called_once_with('/pages/new')
        c.blocks.assert_called_once_with('new')

    def test_proxy_dns_fallback_only_for_known_hosts(self):
        with patch.object(e.socket,'getaddrinfo',side_effect=e.socket.gaierror()), patch.object(e,'getproxies',return_value={'https':'proxy'}):
            self.assertEqual(e.public_url('https://job-boards.greenhouse.io/fixture/jobs/123'),'https://job-boards.greenhouse.io/fixture/jobs/123')
            with self.assertRaises(e.IntakeError):
                e.public_url('https://unknown.example/job')

    def test_greenhouse_uses_verified_board_name_and_posting_id(self):
        data={'id':123,'title':'Engineering Intern','content':'<p>Test hardware.</p>',
              'location':{'name':'Long Beach, CA'},'absolute_url':job()['original_url']}
        with patch.object(e,'fetch',side_effect=[json.dumps(data),json.dumps({'name':'Fixture Co'})]):
            extracted=e.extract_greenhouse(job()['original_url'])
        self.assertEqual(extracted['company'],'Fixture Co')
        self.assertEqual(a.requisition(extracted),'123')
        self.assertEqual(extracted['description'],'Test hardware.')
        self.assertEqual(extracted['inferred_fields'],{})


if __name__=='__main__':
    unittest.main()
