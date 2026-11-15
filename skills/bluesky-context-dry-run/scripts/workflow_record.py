"""Local provenance for workflow stages and revisions; does not execute a model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


MODEL_STAGES = {'goal_operationalization', 'research_plan', 'thematic_selection', 'drafting', 'model_review'}


def executor_label(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', value):
        raise ValueError('Executor needs a short label with letters, digits, dots, underscores or hyphens.')
    return value


def model_stage(data, *, executor='codex'):
    if not isinstance(data, dict) or set(data) != {'kind', 'stage', 'detail'}:
        raise ValueError('A model_stage record requires exactly kind, stage and detail.')
    if not isinstance(data['stage'], str) or data['stage'] not in MODEL_STAGES:
        raise ValueError('Unknown model workflow stage.')
    if not isinstance(data['detail'], str) or not data['detail'].strip():
        raise ValueError('Describe the model work actually performed in the agent runtime.')
    executor = executor_label(executor)
    return {'stage': data['stage'], 'detail': data['detail'], 'actor': 'model', 'executor': executor,
            'separate_model_call': False if executor == 'codex' else None, 'independent_verification': False}


def revision(parent_run=None, reason=None):
    if parent_run is None and reason is None:
        return None
    if parent_run is None or not isinstance(reason, str) or not reason.strip():
        raise ValueError('A revision needs both parent_run and a nonempty revision_reason.')
    parent = Path(parent_run).resolve()
    snapshot = (parent / 'run.json').read_bytes()
    meta = json.loads(snapshot)
    if not isinstance(meta, dict) or meta.get('mode') not in ('codex-dry-run', 'agent-dry-run', 'offline-simulation'):
        raise ValueError('The parent must be an existing dry-run or local simulation.')
    return {'run_id': meta.get('id', parent.name), 'directory': str(parent),
            'run_meta_sha256': hashlib.sha256(snapshot).hexdigest(), 'reason': reason.strip()}
