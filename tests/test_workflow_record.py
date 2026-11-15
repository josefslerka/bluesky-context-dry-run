"""Workflow provenance preserves earlier runs and separates model notes from measurements."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/bluesky-context-dry-run/scripts'))
import bluesky_dry_run as dry
import virtual_amplifier as sim


class WorkflowRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def snapshot(self, path):
        return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob('*') if p.is_file()}

    def test_readonly_revision_links_the_parent_without_modifying_it(self):
        parent = dry.start(None, self.base, topic='Fixture topic')
        before = self.snapshot(parent)
        child = dry.start(None, self.base, topic='Fixture topic', parent_run=parent,
                          revision_reason='The context changed; rebuild the profile.')
        link = dry.read(child / 'run.json')['revision_of']
        self.assertEqual(link['run_id'], parent.name)
        self.assertEqual(link['run_meta_sha256'], hashlib.sha256(before['run.json']).hexdigest())
        self.assertEqual(self.snapshot(parent), before)
        self.assertNotEqual(parent, child)

    def test_local_simulation_revision_preserves_the_parent_queue(self):
        parent = sim.start('Fixture topic', self.base)
        before = self.snapshot(parent)
        child = sim.start('Fixture topic', self.base, parent_run=parent,
                          revision_reason='A new interpretation needs a separate run.')
        self.assertEqual(sim.read(child / 'run.json')['revision_of']['run_id'], parent.name)
        self.assertEqual(self.snapshot(parent), before)
        self.assertEqual(sim.status_data(child)['local_posts'], [])

    def test_codex_stage_records_do_not_claim_independent_review_or_human_work(self):
        path = dry.start(None, self.base, topic='Fixture topic')
        run = dry.Run(path)
        dry.write(path / 'candidates.json', {'candidates': [], 'warnings': []})
        dry.write(path / 'contexts.json', {})
        for stage in ('goal_operationalization', 'model_review'):
            event = dry.add_event(run, {'kind': 'model_stage', 'stage': stage,
                                       'detail': 'Fixture record of model work, not an executed model call.'})
            self.assertEqual(event['actor'], 'model')
            self.assertFalse(event['separate_model_call'])
            self.assertFalse(event['independent_verification'])
        with self.assertRaises(dry.RunError):
            dry.add_event(run, {'kind': 'model_stage', 'stage': 'model_review', 'detail': 'A false claim.',
                                'independent_verification': True})
        result = dry.finalize(run, {'summary': 'No candidate fixture.', 'decisions': [], 'limitations': []})
        self.assertEqual(len(result['model_stages']), 2)
        self.assertEqual(result['measurements']['human_interventions'], 0)
        self.assertEqual(result['measurements']['human_editor_reviews'], 0)
        self.assertIsNone(result['measurements']['actual_cost_usd'])
        self.assertEqual(result['measurements']['public_get_requests'], 0)

    def test_virtual_codex_stage_is_a_log_record_without_a_publication(self):
        path = sim.start('Fixture topic', self.base)
        sim.add_measurement(path, {'kind': 'model_stage', 'stage': 'model_review',
                                  'detail': 'Fixture content review recorded in Codex.'})
        data = sim.status_data(path)
        stages = [e for e in data['coordination_log'] if e['kind'] == 'model_stage']
        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0]['actor'], 'model')
        self.assertFalse(stages[0]['detail']['independent_verification'])
        self.assertFalse(stages[0]['detail']['separate_model_call'])
        self.assertEqual(data['local_posts'], [])
        self.assertFalse(sim.read(path / 'run.json')['publication_enabled'])

    def test_another_executor_is_identified_without_claiming_codex_or_known_api_usage(self):
        read_path = dry.start(None, self.base / 'read', topic='Fixture topic', executor='other-agent')
        event = dry.add_event(dry.Run(read_path), {'kind': 'model_stage', 'stage': 'model_review',
                                                 'detail': 'Fixture review in another host.'})
        self.assertEqual(event['executor'], 'other-agent')
        self.assertIsNone(event['separate_model_call'])
        self.assertEqual(dry.read(read_path / 'run.json')['mode'], 'agent-dry-run')
        sim_path = sim.start('Fixture topic', self.base / 'sim', executor='other-agent')
        sim.add_measurement(sim_path, {'kind': 'model_stage', 'stage': 'model_review',
                                       'detail': 'Fixture review in another host.'})
        event = sim.status_data(sim_path)['coordination_log'][-1]
        self.assertEqual(event['detail']['executor'], 'other-agent')
        self.assertIsNone(event['detail']['separate_model_call'])
        self.assertFalse(event['detail']['independent_verification'])


if __name__ == '__main__':
    unittest.main()
