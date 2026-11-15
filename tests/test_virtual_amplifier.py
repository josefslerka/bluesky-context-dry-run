"""Offline contracts of the real queue, parallel claims, evidence and measurements."""
import copy
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/bluesky-context-dry-run/scripts'))
import virtual_amplifier as sim
import discussion_profile as discussion
from discussion_fixture import profile_for


class VirtualAmplifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.research = self.base / 'research'
        self.research.mkdir()
        self.topic = 'Srozumitelné vysvětlení dat'
        self.path = sim.start(self.topic, self.base / 'runs')
        candidates, contexts, jobs = [], {}, []
        for i, role in enumerate(['data', 'clarification', 'explanation'], 1):
            uri = f'at://did:plc:fixture/app.bsky.feed.post/p{i}'
            p = {'id': f'C-{i}', 'uri': uri, 'root_uri': uri, 'cid': f'fixture-cid-{i}',
                 'handle': 'fixture.example', 'author_did': 'did:plc:fixture',
                 'url': f'https://bsky.app/profile/fixture.example/post/p{i}',
                 'date': '2026-11-14T18:00:00Z', 'text': f'This is a public explanation number {i}.'}
            candidates.append(p)
            contexts[p['id']] = {'valid': True, 'posts': [copy.deepcopy(p)]}
            jobs.append({'candidate_id': p['id'], 'reason': 'Adds a factual distinction.',
                'support_basis': 'Recognizes a specific explanatory contribution.', 'role': role,
                'language': 'en', 'draft_body': f'The distinction in explanation {i} is useful for interpreting the data.',
                'context_evidence': [{'post_uri': uri, 'quote': 'public explanation'}],
                'source_evidence': [{'paragraph_id': 'S001', 'quote': 'These figures are estimates.'}]})
        self.plan = {'topic': self.topic, 'intent': 'support_factual_contribution', 'jobs': jobs,
                     'limitations': [], 'synthetic_reactions': []}
        self.candidates, self.contexts = candidates, contexts
        sim.write(self.research / 'source.json', {'title': 'Fixture', 'url': None,
            'paragraphs': [{'id': 'S001', 'text': 'These figures are estimates.'}]})
        self.save_research()

    def save_research(self):
        sim.write(self.research / 'candidates.json', {'candidates': self.candidates})
        sim.write(self.research / 'contexts.json', self.contexts)
        source = sim.read(self.research / 'source.json')
        profiles = {}
        for candidate in self.candidates:
            try:
                context = self.contexts[candidate['id']]
                profiles[candidate['id']] = discussion.validate(profile_for(candidate, context, source), candidate, context, source)
            except discussion.ProfileError:
                continue
        sim.write(self.research / 'discussion-profiles.json', {'version': 1, 'profiles': profiles})
        for job in self.plan['jobs']:
            job['discussion_profile_id'] = profiles.get(job['candidate_id'], {}).get('profile_id')

    def load(self):
        return sim.load_plan(self.path, self.research, self.plan)

    def test_formal_check_leaves_queue_unreserved_and_load_rechecks_the_final_text(self):
        _, _, checked = sim.check_plan(self.path, self.research, self.plan)
        self.assertEqual(len(checked), 3)
        self.assertTrue(all(error is None for _, error in checked))
        self.assertEqual(sim.status_data(self.path)['queue'], [])
        self.assertFalse((self.path / 'plan.json').exists())
        self.assertFalse((self.path / 'research.json').exists())
        self.plan['jobs'][0]['context_evidence'][0]['quote'] = 'An invented quote added after preflight.'
        self.load()
        result = sim.run(self.path)
        self.assertEqual(result['queue'][0]['status'], 'rejected')
        self.assertIn('Unverified context quote', result['queue'][0]['reason'])
        self.assertEqual(result['measurements']['simulated_posts'], 2)

    def make_fictional_profiles(self):
        for i, (p, job) in enumerate(zip(self.candidates, self.plan['jobs']), 1):
            old_uri = p['uri']
            p.update(uri=f'sim://recipient-{i}/post', root_uri=f'sim://recipient-{i}/post',
                     cid=f'synthetic:cid:{i}', author_did=f'synthetic:persona:P{i}',
                     handle=f'synthetic:persona:P{i}', url=None, origin='synthetic')
            self.contexts[p['id']]['posts'] = [copy.deepcopy(p)]
            job['context_evidence'][0]['post_uri'] = p['uri']
            job['baseline_draft_body'] = f'This is a useful explanation {i} of the data.'
            job['psychological_profile'] = {'kind': 'fictional_hypothesis', 'id': p['author_did'],
                'motivation': 'Understand a distinction.', 'anticipated_emotion': 'Uncertainty about the terminology.',
                'formulation_strategy': 'Name the distinction explicitly.', 'empirical_support': None}
            job['adaptation_trace'] = [{'field': 'motivation', 'before': 'useful explanation',
                'after': 'distinction', 'reason': 'Emphasize the distinction for this invented recipient.'}]
        self.save_research()
        path = self.research / 'candidates.json'
        sim.write(path, {**sim.read(path), 'context_origin': 'synthetic'})

    def test_fictional_profiles_record_baselines_and_wording_traces(self):
        self.make_fictional_profiles()
        self.load()
        result = sim.run(self.path)
        self.assertEqual(result['measurements']['fictional_psychological_profiles'], 3)
        self.assertEqual(result['measurements']['real_psychological_profiles'], 0)
        self.assertEqual(len(result['psychological_profiles']), 3)
        self.assertTrue(all(p['baseline'] != p['adapted'] for p in result['psychological_profiles']))
        self.assertEqual(sum(e['kind'] == 'fictional_profile_applied' for e in result['coordination_log']), 3)
        self.assertIsNone(result['measurements']['observed_real_reach'])

    def test_psychological_profiles_cannot_be_joined_to_real_post_targets(self):
        self.make_fictional_profiles()
        self.candidates[0].update(uri='at://did:plc:real/app.bsky.feed.post/post', root_uri='at://did:plc:real/app.bsky.feed.post/post',
            author_did='did:plc:real', handle='real.example', url='https://bsky.app/profile/real.example/post/post')
        self.contexts['C-1']['posts'] = [copy.deepcopy(self.candidates[0])]
        self.plan['jobs'][0]['context_evidence'][0]['post_uri'] = self.candidates[0]['uri']
        self.save_research()
        path = self.research / 'candidates.json'
        sim.write(path, {**sim.read(path), 'context_origin': 'synthetic'})
        self.load()
        result = sim.run(self.path)
        self.assertEqual(result['queue'][0]['status'], 'rejected')
        self.assertEqual(result['measurements']['fictional_psychological_profiles'], 2)
        self.assertEqual(result['measurements']['simulated_posts'], 2)

    def test_profile_cannot_change_numbers_or_claim_empirical_support(self):
        self.make_fictional_profiles()
        self.plan['jobs'][0]['baseline_draft_body'] = 'This is a useful explanation 100 of the data.'
        self.plan['jobs'][1]['psychological_profile']['empirical_support'] = 'Inferred from a real person.'
        self.load()
        result = sim.run(self.path)
        self.assertEqual(result['measurements']['rejected_jobs'], 2)
        self.assertEqual(result['measurements']['simulated_posts'], 1)

    def test_profile_trace_must_be_present_in_both_texts(self):
        self.make_fictional_profiles()
        self.plan['jobs'][0]['adaptation_trace'][0]['before'] = 'Invented nonexistent text'
        self.plan['jobs'][1]['baseline_draft_body'] = self.plan['jobs'][1]['draft_body']
        self.load()
        result = sim.run(self.path)
        self.assertEqual(result['measurements']['rejected_jobs'], 2)
        self.assertEqual(result['measurements']['simulated_posts'], 1)

    def test_complete_flow_runs_with_network_disabled_and_no_live_ids(self):
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            self.load()
            result = sim.run(self.path)
        self.assertEqual(len(result['local_posts']), 3)
        self.assertTrue(all(p['receipt'].startswith('sim://') for p in result['local_posts']))
        self.assertEqual(result['measurements']['public_network_requests'], 0)
        self.assertEqual(result['measurements']['public_writes'], 0)
        self.assertIsNone(result['measurements']['observed_real_audience_reactions'])
        self.assertIsNone(result['measurements']['actual_cost_usd'])
        self.assertTrue(all('https://' not in p['text'] and '[BotyLab · AI · V' in p['text'] for p in result['local_posts']))
        self.assertEqual({j['account_id'] for j in result['queue']}, {'virtual:V1', 'virtual:V2', 'virtual:V3'})
        for filename in ['report.html', 'report.json', 'queue.csv', 'queue.json', 'coordination.jsonl']:
            self.assertTrue((self.path / filename).is_file())

    def test_duplicate_root_is_held_even_with_another_reply_target(self):
        duplicate = copy.deepcopy(self.plan['jobs'][0])
        duplicate['draft_body'] = 'A second message which must not reach the same thread.'
        self.plan['jobs'].append(duplicate)
        self.load()
        result = sim.run(self.path)
        self.assertEqual(result['queue'][-1]['status'], 'held')
        self.assertIn('thread_already_reserved', result['queue'][-1]['reason'])
        self.assertEqual(len(result['local_posts']), 3)

    def test_concurrent_claims_and_retries_produce_exactly_one_receipt(self):
        self.load()
        def attempt(_):
            job = sim.claim(self.path, 'virtual:V1')
            return sim.local_publish(self.path, job, 'virtual:V1') if job else None
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(attempt, range(24)))
        self.assertEqual(sum(r is not None for r in results), 1)
        original = next(r for r in results if r)
        self.assertEqual(sim.local_publish(self.path, 'J001', 'virtual:V1'), original)
        with self.assertRaises(sim.SimulationError):
            sim.local_publish(self.path, 'J001', 'virtual:V2')
        data = sim.status_data(self.path)
        self.assertEqual(len(data['local_posts']), 1)
        self.assertEqual(sum(e['kind'] == 'simulated_published' for e in data['coordination_log']), 1)

    def test_changed_cid_fabricated_quote_and_unverified_target_are_rejected(self):
        self.contexts['C-1']['posts'][0]['cid'] = 'changed'
        self.plan['jobs'][1]['context_evidence'][0]['quote'] = 'A fabricated quotation.'
        self.plan['jobs'][2]['reply_to_uri'] = 'at://did:plc:other/app.bsky.feed.post/unverified'
        self.save_research()
        self.load()
        result = sim.run(self.path)
        self.assertEqual(result['measurements']['rejected_jobs'], 3)
        self.assertEqual(result['local_posts'], [])

    def test_urls_and_overlong_text_never_enter_local_outbox(self):
        self.plan['jobs'][0]['draft_body'] = 'Look at https://example.com'
        self.plan['jobs'][1]['draft_body'] = 'x' * 300
        self.load()
        result = sim.run(self.path)
        self.assertEqual(result['measurements']['rejected_jobs'], 2)
        self.assertEqual(len(result['local_posts']), 1)

    def test_account_language_and_capacity_can_leave_account_idle(self):
        self.plan['jobs'][0]['language'] = 'es'  # V1 is not assigned Spanish.
        self.load()
        result = sim.run(self.path)
        self.assertEqual(result['queue'][0]['status'], 'held')
        self.assertEqual(result['measurements']['simulated_posts'], 2)
        self.assertTrue(any(e['kind'] == 'account_idle' and e['actor'] == 'virtual:V1' for e in result['coordination_log']))

    def test_synthetic_network_activity_is_separate_from_real_effect(self):
        self.plan['synthetic_reactions'] = [
            {'job_id': 'J001', 'actor': 'virtual:V2', 'kind': 'like'},
            {'job_id': 'J001', 'actor': 'synthetic:reader-1', 'kind': 'reply'},
            {'job_id': 'J002', 'actor': 'synthetic:reader-1', 'kind': 'repost'},
            {'job_id': 'J003', 'actor': 'synthetic:reader-2', 'kind': 'like'}]
        self.load()
        m = sim.run(self.path)['measurements']
        self.assertEqual(m['synthetic_own_network_reactions'], 1)
        self.assertEqual(m['synthetic_external_reactions'], 3)
        self.assertEqual(m['synthetic_external_actors'], 2)
        self.assertIsNone(m['observed_real_reach'])

    def test_human_wait_is_not_active_work_and_partial_cost_is_not_total(self):
        self.load()
        t = sim.now()
        with patch.object(sim, 'now', return_value=t):
            request = sim.add_measurement(self.path, {'kind': 'human_request', 'reason': 'Fixture question'})
        with patch.object(sim, 'now', return_value=t + dt.timedelta(seconds=24)):
            sim.add_measurement(self.path, {'kind': 'human_response', 'request_id': request})
        sim.add_measurement(self.path, {'kind': 'usage', 'provider': 'fixture', 'measurement_source': 'fixture response', 'cost_usd': .02})
        m = sim.run(self.path)['measurements']
        self.assertEqual(m['human_interventions'], 1)
        self.assertAlmostEqual(m['human_waiting_seconds'], 24, places=2)
        self.assertIsNone(m['human_active_seconds'])
        self.assertEqual(m['recorded_partial_cost_usd'], .02)
        self.assertIsNone(m['actual_cost_usd'])
        self.assertEqual(m['usage_coverage'], 'partial')

    def test_html_and_placeholder_text_cannot_break_embedded_json(self):
        payload = '</script><img src=x onerror=alert(1)> __NOSCRIPT_QUEUE__ __REPORT_DATA__'
        self.plan['jobs'][0]['draft_body'] = payload
        self.load()
        result = sim.run(self.path)
        page = (self.path / 'report.html').read_text()
        self.assertNotIn('<img src=x', page)
        raw = page.split('<script id="report-data" type="application/json">', 1)[1].split('</script>', 1)[0]
        self.assertEqual(json.loads(raw), result)

    def test_completed_simulation_and_loaded_plan_cannot_be_overwritten(self):
        self.load()
        with self.assertRaises(sim.SimulationError):
            self.load()
        sim.run(self.path)
        original = (self.path / 'report.json').read_bytes()
        with self.assertRaises(sim.SimulationError):
            sim.run(self.path)
        with self.assertRaises(sim.SimulationError):
            sim.add_measurement(self.path, {'kind': 'note', 'detail': 'Attempted rewrite'})
        self.assertEqual((self.path / 'report.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
