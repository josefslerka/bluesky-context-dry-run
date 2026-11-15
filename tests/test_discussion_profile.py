"""Profiles bind decisions to actual thread evidence and are enforced before drafts."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/bluesky-context-dry-run/scripts'))
import discussion_profile as dp
import bluesky_dry_run as dry
import virtual_amplifier as sim
from discussion_fixture import profile_for


class DiscussionProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.uri = 'at://did:plc:fixture/app.bsky.feed.post/root'
        self.post = {'id': 'C-one', 'uri': self.uri, 'root_uri': self.uri, 'cid': 'fixture-cid',
                     'handle': 'fixture.example', 'author_did': 'did:plc:fixture',
                     'url': 'https://bsky.app/profile/fixture.example/post/root',
                     'date': '2026-11-14T12:00:00Z', 'text': 'Which supplier costs can be independently checked?'}
        self.context = {'valid': True, 'posts': [self.post], 'scope': 'One bounded fixture post.'}
        self.source = {'url': 'https://publisher.example/source', 'title': 'Supplier case', 'text_kind': 'excerpt',
                       'paragraphs': [{'id': 'S001', 'text': 'The supplier costs were not disclosed.'}]}
        self.raw = profile_for(self.post, self.context, self.source)
        self.stored = dp.validate(self.raw, self.post, self.context, self.source)

    def test_profile_records_observed_context_and_explicit_inferred_gap(self):
        raw = copy.deepcopy(self.raw)
        raw['open_questions'] = [{'question': 'Could this be compared with another supplier?', 'kind': 'inferred_gap',
                                 'evidence': [{'post_uri': self.uri, 'quote': self.post['text']}]}]
        result = dp.validate(raw, self.post, self.context, self.source)
        self.assertEqual(result['observed_posts'], 1)
        self.assertEqual(result['open_questions'][0]['kind'], 'inferred_gap')
        self.assertEqual(dp.ensure_current(result, self.post, self.context, self.source), result)

    def test_fabricated_quote_and_unobserved_post_are_rejected(self):
        for quote in [{'post_uri': self.uri, 'quote': 'A nonexistent quotation.'},
                      {'post_uri': 'at://did:plc:unread/app.bsky.feed.post/post', 'quote': self.post['text']}]:
            raw = copy.deepcopy(self.raw)
            raw['arguments'][0]['evidence'] = [quote]
            with self.assertRaises(dp.ProfileError):
                dp.validate(raw, self.post, self.context, self.source)

    def test_changed_source_or_context_invalidates_the_profile(self):
        context = copy.deepcopy(self.context)
        context['posts'][0]['text'] += ' New information.'
        with self.assertRaisesRegex(dp.ProfileError, 'context changed'):
            dp.ensure_current(self.stored, self.post, context, self.source)
        source = copy.deepcopy(self.source)
        source['paragraphs'][0]['text'] = 'Costs were disclosed later.'
        with self.assertRaisesRegex(dp.ProfileError, 'source changed'):
            dp.ensure_current(self.stored, self.post, self.context, source)

    def test_skip_and_unlinked_profile_prevent_a_reply(self):
        raw = profile_for(self.post, self.context, self.source, 'skip')
        stored = dp.validate(raw, self.post, self.context, self.source)
        with self.assertRaisesRegex(dp.ProfileError, 'says skip'):
            dp.gate(stored, self.post, self.context, self.source, stored['profile_id'], True)
        with self.assertRaisesRegex(dp.ProfileError, 'discussion_profile_id'):
            dp.gate(self.stored, self.post, self.context, self.source, 'DP-another', True)
        self.assertEqual(dp.gate(stored, self.post, self.context, self.source, stored['profile_id'], False), stored)

    def test_profile_is_not_an_author_personality_container(self):
        raw = copy.deepcopy(self.raw)
        raw['author_motivation'] = 'A guessed private motive.'
        with self.assertRaisesRegex(dp.ProfileError, 'unsupported fields'):
            dp.validate(raw, self.post, self.context, self.source)

    def test_relevant_support_reaches_report_and_queue_without_new_information(self):
        # The source and the post say the same thing; no open question or new fact is needed.
        post = {**self.post, 'text': self.source['paragraphs'][0]['text']}
        context = {**self.context, 'posts': [post]}
        path = dry.start(self.source['url'], self.base / 'read-runs')
        run = dry.Run(path)
        source = dry.capture_source(run, {**self.source, 'language': 'en',
            'paragraphs': [p['text'] for p in self.source['paragraphs']]})
        dry.write(path / 'candidates.json', {'candidates': [post], 'warnings': []})
        dry.write(path / 'contexts.json', {post['id']: context})
        raw = profile_for(post, context, source)
        saved = dry.capture_discussion_profiles(run, {'profiles': [raw]})['profiles'][post['id']]
        common = {'candidate_id': post['id'], 'discussion_profile_id': saved['profile_id'],
                  'reason': 'The reply supports this same supplier-cost topic.', 'language': 'en',
                  'draft_body': 'The costs remain undisclosed, as your post explains.',
                  'context_evidence': raw['contribution']['context_evidence'],
                  'source_evidence': raw['contribution']['source_evidence']}
        assessment = {'summary': 'Contextual support without a new fact.', 'limitations': [],
            'decisions': [{**common, 'decision': 'select', 'relation': 'direct',
                           'context_connection': 'Both texts discuss undisclosed supplier costs.'}]}
        result = dry.finalize(run, assessment)
        self.assertEqual(result['selected_count'], 1)
        self.assertIsNone(result['decisions'][0].get('added_information'))
        self.assertIsNone(saved['contribution']['added_value'])
        self.assertEqual(saved['open_questions'], [])
        self.assertNotIn('Volitelná doplňující informace:', (path / 'report.html').read_text())
        sim_path = sim.start('Supplier-cost discussion', self.base / 'sim-runs')
        plan = {'topic': 'Supplier-cost discussion', 'intent': 'support_factual_contribution',
            'jobs': [{**common, 'decision': 'reply', 'role': 'clarification',
                      'support_basis': 'Support the same already stated point.'}], 'synthetic_reactions': []}
        sim.load_plan(sim_path, path, plan)
        result = sim.run(sim_path)
        self.assertEqual(len(result['local_posts']), 1)
        self.assertEqual(result['discussion_profile_criterion'], 'thematic_fit')
        self.assertEqual(result['public_writes'], 0)

    def test_new_information_does_not_override_a_thematic_mismatch(self):
        path = dry.start(self.source['url'], self.base / 'read-runs')
        run = dry.Run(path)
        for name, data in [('source.json', self.source), ('candidates.json', {'candidates': [self.post]}),
                           ('contexts.json', {self.post['id']: self.context})]:
            dry.write(path / name, data)
        saved = dry.capture_discussion_profiles(run, {
            'profiles': [profile_for(self.post, self.context, self.source, 'skip')]})['profiles'][self.post['id']]
        assessment = {'summary': 'Attempt to use novelty to enter a different topic.', 'limitations': [],
            'decisions': [{'candidate_id': self.post['id'], 'discussion_profile_id': saved['profile_id'],
                          'decision': 'select', 'relation': 'direct', 'reason': 'A new fact exists.',
                          'added_information': 'A completely new fact about another topic.'}]}
        with self.assertRaisesRegex(dry.RunError, 'says skip'):
            dry.finalize(run, assessment)
        self.assertFalse((path / 'report.json').exists())

    def test_legacy_records_remain_readable_but_need_thematic_reassessment_for_new_runs(self):
        raw = copy.deepcopy(self.raw)
        for name in ('criterion', 'connection', 'reply_mode'):
            raw['contribution'].pop(name)
        raw['contribution']['added_value'] = 'A fact considered new by the former selection criterion.'
        legacy = dp.validate(raw, self.post, self.context, self.source)
        self.assertEqual(dp.ensure_current(legacy, self.post, self.context, self.source), legacy)
        with self.assertRaisesRegex(dp.ProfileError, 'requires a thematic_fit profile'):
            dp.gate(legacy, self.post, self.context, self.source, legacy['profile_id'], True,
                    criterion=dp.THEMATIC_FIT)
        path = dry.start(self.source['url'], self.base / 'read-runs')
        for name, data in [('source.json', self.source), ('candidates.json', {'candidates': [self.post]}),
                           ('contexts.json', {self.post['id']: self.context})]:
            dry.write(path / name, data)
        with self.assertRaisesRegex(dry.RunError, 'requires a thematic_fit profile'):
            dry.capture_discussion_profiles(dry.Run(path), {'profiles': [raw]})
        self.assertFalse((path / 'discussion-profiles.json').exists())

    def test_profiles_are_frozen_before_read_only_finalization(self):
        path = dry.start('https://publisher.example/source', self.base / 'read-runs')
        run = dry.Run(path)
        for name, data in [('source.json', self.source), ('candidates.json', {'candidates': [self.post]}),
                           ('contexts.json', {self.post['id']: self.context})]:
            dry.write(path / name, data)
        saved = dry.capture_discussion_profiles(run, {'profiles': [self.raw]})
        self.assertEqual(saved['profiles'][self.post['id']]['profile_id'], self.stored['profile_id'])
        frozen = [e for e in run.events() if e['kind'] == 'discussion_profile_frozen'][0]
        self.assertEqual(frozen['actor'], 'program')
        self.assertFalse(frozen['interpretation_verified'])
        with self.assertRaisesRegex(dry.RunError, 'already frozen'):
            dry.capture_discussion_profiles(run, {'profiles': [self.raw]})
        self.assertFalse((path / 'report.json').exists())

    def test_public_simulation_cannot_bypass_missing_or_skip_profile(self):
        research = self.base / 'research'
        research.mkdir()
        for name, data in [('source.json', self.source), ('candidates.json', {'candidates': [self.post]}),
                           ('contexts.json', {self.post['id']: self.context})]:
            sim.write(research / name, data)
        for origin, use_skip in [('public_snapshot', False), ('synthetic', False),
                                 ('consented_participant_invitation', False), ('unknown', False),
                                 ('public_snapshot', True)]:
            sim.write(research / 'candidates.json', {'context_origin': origin, 'candidates': [self.post]})
            path = sim.start('Supplier explanation', self.base / 'sim-runs')
            stored = dp.validate(profile_for(self.post, self.context, self.source, 'skip'), self.post, self.context, self.source)
            if use_skip:
                sim.write(research / 'discussion-profiles.json', {'version': 1, 'profiles': {self.post['id']: stored}})
            plan = {'topic': 'Supplier explanation', 'intent': 'support_factual_contribution', 'jobs': [{
                'candidate_id': self.post['id'], 'discussion_profile_id': stored['profile_id'],
                'decision': 'reply', 'reason': 'An attempted reply which should be blocked.', 'role': 'data', 'language': 'en',
                'support_basis': 'A claimed comparison.', 'draft_body': 'This would be an unsupported reply.',
                'context_evidence': [{'post_uri': self.uri, 'quote': self.post['text']}]}], 'synthetic_reactions': []}
            sim.load_plan(path, research, plan)
            result = sim.run(path)
            self.assertEqual(result['local_posts'], [])
            self.assertEqual(result['queue'][0]['status'], 'rejected')
            self.assertIn('says skip' if use_skip else 'required before drafting', result['queue'][0]['reason'])


if __name__ == '__main__':
    unittest.main()
