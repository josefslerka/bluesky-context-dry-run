"""Run the exported bundle from a fresh path with networking disabled."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_portable_bundle as bundle


class PortableBundleTests(unittest.TestCase):
    def test_exported_demo_works_without_the_checkout_or_network(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            first, second = base / 'first.zip', base / 'second.zip'
            bundle.build(first)
            bundle.build(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            extraction = base / 'other machine with spaces'
            with zipfile.ZipFile(first) as archive:
                self.assertFalse(any('.env' in n or '__pycache__' in n or '/output/' in n for n in archive.namelist()))
                archive.extractall(extraction)
            portable = extraction / bundle.BUNDLE_ROOT
            manifest = json.loads((portable / 'bundle-manifest.json').read_text())
            for name, item in manifest['files'].items():
                data = (portable / name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
                self.assertNotIn(b'/Users/', data)
            runner = portable / 'skills/bluesky-context-dry-run/scripts/offline_demo.py'
            other_cwd = base / 'unrelated working directory'
            other_cwd.mkdir()
            output = base / 'local outputs'
            code = '''import runpy, socket, sys
def no_network(*args, **kwargs):
    raise AssertionError("Portable demo attempted a network call")
socket.socket = no_network
socket.create_connection = no_network
sys.path.insert(0, sys.argv[1])
sys.argv = [sys.argv[2], "--output-root", sys.argv[3]]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
            completed = subprocess.run([sys.executable, '-c', code, str(runner.parent), str(runner), str(output)],
                                       cwd=other_cwd, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            report = json.loads((Path(result['run_dir']) / 'report.json').read_text())
            self.assertTrue(Path(result['report']).is_file())
            self.assertTrue(result['preauthored_fixture'])
            self.assertFalse(result['new_model_inference'])
            self.assertEqual(report['model_executor'], 'recorded-fixture')
            self.assertEqual(report['model_stages'], [])
            self.assertEqual(len(report['local_posts']), 3)
            self.assertEqual(report['measurements']['fictional_psychological_profiles'], 3)
            self.assertEqual(report['measurements']['real_psychological_profiles'], 0)
            self.assertEqual(report['measurements']['public_network_requests'], 0)
            self.assertIsNone(report['measurements']['actual_cost_usd'])
            self.assertEqual(report['public_writes'], 0)


if __name__ == '__main__':
    unittest.main()
