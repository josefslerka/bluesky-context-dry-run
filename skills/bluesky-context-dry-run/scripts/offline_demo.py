"""Replay preauthored fictional data locally. No network or new model inference."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import virtual_amplifier as simulator


def demo(output_root):
    fixture = simulator.read(Path(__file__).resolve().parents[1] / 'assets' / 'fictional-demo.json')
    simulator.require(fixture.get('fixture_kind') == 'preauthored_synthetic_example'
                      and fixture['candidates'].get('context_origin') == 'synthetic',
                      'The offline demo requires a preauthored synthetic fixture.')
    path = simulator.start(fixture['plan']['topic'], output_root, executor='recorded-fixture')
    research = path / 'synthetic-research'
    research.mkdir()
    for key in ('source', 'candidates', 'contexts'):
        simulator.write(research / (key + '.json'), fixture[key])
    simulator.write(path / 'plan-input.json', fixture['plan'])
    simulator.add_measurement(path, {'kind': 'note', 'detail':
        'Přehrání předpřipravených fiktivních výstupů. Žádná nová modelová inference '
        'ani rešerše. Měřený čas patří lokálnímu přehrání, ne tvorbě návrhů.'})
    _, _, checked = simulator.check_plan(path, research, fixture['plan'])
    simulator.require(all(error is None for _, error in checked), 'The bundled fixture failed validation.')
    simulator.load_plan(path, research, fixture['plan'])
    result = simulator.run(path)
    return {'run_dir': str(path), 'report': str(path / 'report.html'), 'preauthored_fixture': True,
            'new_model_inference': False, 'measurements': result['measurements'], 'public_writes': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', default='output/portable-demo')
    args = parser.parse_args()
    print(json.dumps(demo(Path(args.output_root)), ensure_ascii=False))


if __name__ == '__main__':
    main()
