"""Content profiles of bounded discussions. Checks evidence; does not infer personalities."""
from __future__ import annotations

import hashlib
import html
import json


FIELDS = {'candidate_id', 'topic', 'main_question', 'language', 'tone', 'arguments',
          'already_covered', 'open_questions', 'contribution', 'limitations'}
THEMATIC_FIT = 'thematic_fit'
REPLY_MODES = {'support', 'clarification', 'example', 'question'}


class ProfileError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProfileError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def context_digest(context):
    return digest({**context, 'posts': sorted(context.get('posts', []), key=lambda p: p['uri'])})


def text(value, label):
    require(isinstance(value, str) and 3 <= len(value.strip()) <= 4000, f'Invalid discussion profile {label}.')


def evidence(items, records, key, label, required=True):
    require(isinstance(items, list) and (items or not required) and len(items) <= 12, f'Missing or invalid {label} evidence.')
    for item in items:
        require(isinstance(item, dict) and set(item) == {key, 'quote'}, f'Invalid {label} evidence fields.')
        quote = item.get('quote')
        require(isinstance(quote, str) and len(quote.strip()) >= 8 and quote in records.get(item[key], ''),
                f'Discussion profile {label} quote is not in the frozen evidence.')


def validate(raw, candidate, context, source):
    require(isinstance(raw, dict) and set(raw) == FIELDS, 'Discussion profile has missing or unsupported fields.')
    require(raw['candidate_id'] == candidate['id'], 'Discussion profile belongs to another candidate.')
    require(context.get('valid'), 'Discussion profile requires a valid context.')
    posts = {p['uri']: p for p in context.get('posts', [])}
    anchor = posts.get(candidate['uri'])
    require(anchor and anchor['cid'] == candidate['cid'], 'Discussion profile anchor CID changed.')
    texts = {uri: p['text'] for uri, p in posts.items()}
    paragraphs = {p['id']: p['text'] for p in source.get('paragraphs', [])}
    for key in ('topic', 'main_question', 'language'):
        if key == 'language':
            require(isinstance(raw[key], str) and 2 <= len(raw[key]) <= 20, 'Invalid discussion language.')
        else:
            text(raw[key], key)
    tone = raw['tone']
    require(isinstance(tone, dict) and set(tone) == {'label', 'description', 'evidence'}, 'Invalid discussion tone.')
    require(tone['label'] in ('factual', 'critical', 'mixed', 'unclear'), 'Unsupported discussion tone label.')
    text(tone['description'], 'tone description')
    evidence(tone['evidence'], texts, 'post_uri', 'tone')
    for key in ('arguments', 'already_covered'):
        items = raw[key]
        require(isinstance(items, list) and len(items) <= 12 and (items or key != 'arguments'), f'Invalid discussion {key}.')
        for item in items:
            require(isinstance(item, dict) and set(item) == {'summary', 'evidence'}, f'Invalid discussion {key} fields.')
            text(item['summary'], key)
            evidence(item['evidence'], texts, 'post_uri', key)
    require(isinstance(raw['open_questions'], list) and len(raw['open_questions']) <= 12, 'Invalid open questions.')
    for item in raw['open_questions']:
        require(isinstance(item, dict) and set(item) == {'question', 'kind', 'evidence'}, 'Invalid open-question fields.')
        require(item['kind'] in ('explicit', 'inferred_gap'), 'Open question must distinguish observation and inference.')
        text(item['question'], 'open question')
        evidence(item['evidence'], texts, 'post_uri', 'open question')
    entry = raw['contribution']
    legacy_fields = {'decision', 'reason', 'added_value', 'context_evidence', 'source_evidence'}
    thematic_fields = legacy_fields | {'criterion', 'connection', 'reply_mode'}
    require(isinstance(entry, dict) and set(entry) in (legacy_fields, thematic_fields), 'Invalid contribution fields.')
    thematic = 'criterion' in entry
    if thematic:
        require(entry['criterion'] == THEMATIC_FIT, 'Discussion selection must use thematic_fit.')
        text(entry['connection'], 'thematic connection')
        require(entry['reply_mode'] in REPLY_MODES if entry['decision'] == 'reply' else entry['reply_mode'] is None,
                'A thematic reply needs a supported reply_mode; skipped discussions have none.')
    require(entry['decision'] in ('reply', 'skip'), 'Invalid discussion-entry decision.')
    text(entry['reason'], 'entry reason')
    evidence(entry['context_evidence'], texts, 'post_uri', 'contribution')
    evidence(entry['source_evidence'], paragraphs, 'paragraph_id', 'source',
             required=entry['decision'] == 'reply' and source.get('text_kind') != 'topic_brief')
    if entry['decision'] == 'reply' and (not thematic or entry['added_value'] is not None):
        text(entry['added_value'], 'added value')
    elif entry['decision'] == 'skip':
        require(entry['added_value'] is None, 'Skipped discussions cannot claim a proposed added value.')
    require(isinstance(raw['limitations'], list) and raw['limitations']
            and all(isinstance(v, str) and v.strip() for v in raw['limitations']), 'Discussion profile needs scope limitations.')
    bound = {'context_sha256': context_digest(context), 'source_sha256': digest(source)}
    return {**raw, **bound, 'profile_id': 'DP-' + digest({'profile': raw, **bound})[:12],
            'anchor_uri': candidate['uri'], 'anchor_cid': candidate['cid'],
            'observed_posts': len(posts), 'scope': context.get('scope', 'Bounded frozen context, not the complete discussion.')}


def ensure_current(stored, candidate, context, source):
    require(isinstance(stored, dict), 'A discussion profile is required before drafting.')
    require(stored.get('context_sha256') == context_digest(context), 'Discussion profile is stale: context changed.')
    require(stored.get('source_sha256') == digest(source), 'Discussion profile is stale: source changed.')
    checked = validate({k: stored.get(k) for k in FIELDS}, candidate, context, source)
    require(stored == checked, 'Discussion profile differs from its validated record.')
    return checked


def require_criterion(profile, criterion):
    require(not criterion or profile['contribution'].get('criterion') == criterion,
            'This run requires a thematic_fit profile; reassess the archived context in a new profile run.')


def gate(stored, candidate, context, source, linked_id, wants_reply, *, criterion=None):
    checked = ensure_current(stored, candidate, context, source)
    require_criterion(checked, criterion)
    require(linked_id == checked['profile_id'], 'Draft must reference its discussion_profile_id.')
    require(not wants_reply or checked['contribution']['decision'] == 'reply',
            'Discussion profile says skip: ' + checked['contribution']['reason'])
    return checked


def html_view(profile):
    e = lambda value: html.escape(str(value))
    items = lambda rows, key: '<ul>' + ''.join('<li>' + e(row[key]) + '</li>' for row in rows) + '</ul>'
    entry = profile['contribution']
    return ('<details><summary>Profil diskuse · ' + e(profile['profile_id']) + '</summary>'
            + ('<p><strong>Hlavní filtr: tematická vhodnost.</strong></p><p>' + e(entry['connection']) + '</p>'
               '<p>Způsob reakce: ' + e(entry['reply_mode'] or 'vynechat') + '</p>' if entry.get('criterion') == THEMATIC_FIT else '')
            + '<p><strong>Otázka:</strong> ' + e(profile['main_question']) + '</p>'
            '<p><strong>Jazyk a tón:</strong> ' + e(profile['language']) + ' · ' + e(profile['tone']['description']) + '</p>'
            '<p><strong>Argumenty</strong></p>' + items(profile['arguments'], 'summary') +
            '<p><strong>Co už zaznělo</strong></p>' + items(profile['already_covered'], 'summary') +
            '<p><strong>Otevřené otázky ve výřezu</strong></p>' + items(profile['open_questions'], 'question') +
            '<p><strong>' + ('Navržen vstup' if entry['decision'] == 'reply' else 'Nereagovat') + ':</strong> ' + e(entry['reason']) + '</p>'
            '<p>' + e(entry['added_value'] or '') + '</p><p>' + e(profile['scope']) + '</p></details>')
