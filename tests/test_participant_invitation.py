"""Consenting-participant invitation stays separate from public-thread amplification."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/bluesky-context-dry-run/scripts'))
import participant_invitation as invite
import virtual_amplifier as sim


class ParticipantInvitationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.path = sim.start('Technický experiment', self.base / 'runs')
        did = 'did:plc:fixture-consenting-participant'
        self.posts = [{'id': f'P-{i}', 'uri': f'at://{did}/app.bsky.feed.post/p{i}',
                       'cid': f'fixture-cid-{i}', 'url': f'https://bsky.app/profile/participant.example/post/p{i}',
                       'date': '2025-12-01T12:00:00Z', 'text': f'Zkouším technický experiment číslo {i}.'} for i in (1, 2)]
        self.inputs = {
            'corpus': {'participant_did': did, 'posts': self.posts},
            'estimate': {'participant': 'Josef Šlerka', 'validated': False,
                'corpus': {'posts': 2, 'date_from': self.posts[0]['date'], 'date_to': self.posts[1]['date']},
                'interpretations': [{'dimension': 'open_mindedness', 'estimate': 'výrazná', 'evidence_ids': ['P-1', 'P-2']}],
                'evidence': [{k: p[k] for k in ('id', 'text', 'url', 'date')} for p in self.posts]},
            'consent': {'participant_name': 'Josef Šlerka', 'participant_handle': 'participant.example',
                'participant_did': did, 'salutation': 'Josefe', 'scope': invite.SCOPE,
                'profile_permission_quote': 'Začneme mým vlastním profilem.',
                'invitation_permission_quote': 'Ukaž mi technickou pozvánku.',
                'confirmed_preference': {'pattern': 'testable_experiment', 'quote': 'Tato konkrétní pozvánka se mi líbí.'}}}

    def prepare(self):
        paths = []
        for name in ('estimate', 'corpus', 'consent'):
            path = self.base / (name + '.json')
            sim.write(path, self.inputs[name])
            paths.append(path)
        return sim.prepare_invitation(self.path, *paths)

    def test_invitation_uses_evidence_and_feedback_and_only_one_local_worker(self):
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            self.prepare()
            result = sim.run(self.path)
        self.assertEqual(result['measurements']['simulated_posts'], 1)
        self.assertEqual(result['measurements']['public_writes'], 0)
        self.assertEqual(result['measurements']['consented_participant_invitations'], 1)
        self.assertEqual(sum(e['kind'] == 'account_idle' for e in result['coordination_log']), 2)
        invitation = result['participant_invitations'][0]
        self.assertEqual(invitation['selection_basis'], ['profile_hypothesis', 'participant_confirmed_preference'])
        self.assertEqual(invitation['used_profile_dimensions'], ['open_mindedness'])
        self.assertEqual(invitation['profile_validated'], False)
        self.assertIsNone(invitation['public_target'])
        self.assertTrue(result['local_posts'][0]['text'].startswith('[BotyLab · AI · V3] Josefe, co tu tezi'))

    def test_missing_consent_stops_before_populating_queue(self):
        self.inputs['consent']['scope'] = 'unspecified'
        with self.assertRaises(sim.SimulationError):
            self.prepare()
        self.assertEqual(sim.status_data(self.path)['queue'], [])

    def test_wrong_person_or_fabricated_evidence_is_rejected(self):
        wrong = copy.deepcopy(self.inputs)
        wrong['corpus']['participant_did'] = 'did:plc:someone-else'
        with self.assertRaises(ValueError):
            invite.derive(wrong)
        wrong = copy.deepcopy(self.inputs)
        wrong['estimate']['evidence'][0]['text'] = 'A fabricated source quotation.'
        with self.assertRaises(ValueError):
            invite.derive(wrong)

    def test_unknown_trait_and_no_feedback_falls_back_to_neutral_invitation(self):
        self.inputs['estimate']['interpretations'][0]['estimate'] = None
        self.inputs['consent']['confirmed_preference'] = None
        self.prepare()
        result = sim.run(self.path)
        case = result['participant_invitations'][0]
        self.assertEqual(case['pattern'], 'neutral_invitation')
        self.assertEqual(case['baseline'], case['adapted'])
        self.assertEqual(case['used_profile_dimensions'], [])
        self.assertEqual(result['measurements']['real_psychological_profiles'], 0)

    def test_direct_preference_does_not_become_a_personality_inference(self):
        self.inputs['estimate']['interpretations'][0]['estimate'] = None
        case = invite.derive(self.inputs)
        self.assertEqual(case['pattern'], 'testable_experiment')
        self.assertEqual(case['selection_basis'], ['participant_confirmed_preference'])
        self.assertEqual(case['used_profile_dimensions'], [])
        self.assertIsNone(case['profile_hypothesis'])

    def test_private_invitation_cannot_be_attached_to_a_public_post(self):
        case = invite.make_case(self.inputs, 'Technický experiment', sim.iso())
        research = {k: case[k] for k in ('source', 'candidates', 'contexts', 'invitation_context')}
        item = case['plan']['jobs'][0]
        target = research['contexts'][item['candidate_id']]['posts'][0]
        target['uri'] = 'at://did:plc:fixture/app.bsky.feed.post/public'
        target['root_uri'] = target['uri']
        target['url'] = 'https://bsky.app/profile/fixture.example/post/public'
        research['candidates']['candidates'][0] = copy.deepcopy(target)
        item['context_evidence'][0]['post_uri'] = target['uri']
        with self.assertRaises(ValueError):
            sim.validate_job(item, research)

    def test_arbitrary_message_and_salutation_injection_are_rejected(self):
        case = invite.make_case(self.inputs, 'Technický experiment', sim.iso())
        research = {k: case[k] for k in ('source', 'candidates', 'contexts', 'invitation_context')}
        item = case['plan']['jobs'][0]
        item['draft_body'] = 'Another message outside the scoped technical invitation.'
        with self.assertRaises(ValueError):
            sim.validate_job(item, research)
        self.inputs['consent']['salutation'] = 'Josefe https://example.com'
        with self.assertRaises(ValueError):
            invite.derive(self.inputs)


if __name__ == '__main__':
    unittest.main()
