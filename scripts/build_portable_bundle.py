"""Package the dry-run skill, model instructions and synthetic demo; stdlib only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SKILL_FILES = (
    'SKILL.md', 'agents/openai.yaml',
    'references/formats.md', 'references/workflow.md', 'references/discussion-profile.md',
    'references/virtual-simulation.md', 'references/model-instructions.md',
    'scripts/bluesky_dry_run.py', 'scripts/virtual_amplifier.py', 'scripts/discussion_profile.py',
    'scripts/participant_invitation.py', 'scripts/workflow_record.py', 'scripts/offline_demo.py',
    'assets/virtual-report.html', 'assets/fictional-demo.json',
)
BUNDLE_ROOT = 'bluesky-dry-run-portable'


def build(output):
    skill = ROOT / 'skills' / 'bluesky-context-dry-run'
    entries = {'skills/bluesky-context-dry-run/' + name: (skill / name).read_bytes() for name in SKILL_FILES}
    entries['README.md'] = (ROOT / 'portable' / 'README.md').read_bytes()
    entries['MODEL_INSTRUCTIONS.md'] = (skill / 'references' / 'model-instructions.md').read_bytes()
    manifest = {'format_version': 1, 'publication_enabled': False,
                'offline_demo': 'preauthored synthetic fixture; no new model inference',
                'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                          for name, data in sorted(entries.items())}}
    entries['bundle-manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.tmp')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(BUNDLE_ROOT + '/' + name, date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    temporary.replace(output)
    return {'archive': str(output), 'files': len(entries), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'public_writes': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=str(ROOT / 'output' / 'bluesky-dry-run-portable.zip'))
    print(json.dumps(build(parser.parse_args().out), ensure_ascii=False))
