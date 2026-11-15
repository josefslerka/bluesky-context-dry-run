"""Evidence-backed choice of a private, nonpolitical technical invitation. Offline only."""
from __future__ import annotations

import hashlib
import re

SCOPE = 'private_nonpolitical_technical_invitation'
ORIGIN = 'consented_participant_invitation'
TEMPLATE_ID = 'technical_amplifier_comparison_v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def derive(inputs):
    estimate, corpus, consent = inputs['estimate'], inputs['corpus'], inputs['consent']
    require(consent.get('scope') == SCOPE, 'Participant consent must cover this private technical invitation.')
    for key in ('participant_name', 'participant_handle', 'participant_did', 'salutation',
                'profile_permission_quote', 'invitation_permission_quote'):
        require(isinstance(consent.get(key), str) and consent[key].strip(), 'Incomplete participant consent.')
    require(len(consent['profile_permission_quote']) >= 8 and len(consent['invitation_permission_quote']) >= 8,
            'Consent needs the actual participant statements.')
    name = consent['salutation']
    require(len(name) <= 40 and re.fullmatch(r'[^\W\d_]+(?:[ -][^\W\d_]+)*', name), 'Invalid salutation.')
    did = consent['participant_did']
    require(did.startswith('did:plc:') and corpus.get('participant_did') == did, 'Corpus belongs to another participant.')
    require(estimate.get('participant') == consent['participant_name'], 'Estimate belongs to another participant.')
    require(estimate.get('validated') is False, 'This branch accepts a labelled informal estimate, not a claimed test result.')
    posts = corpus.get('posts', [])
    require(posts and estimate.get('corpus', {}).get('posts') == len(posts), 'Corpus size does not match the estimate.')
    by_id = {p['id']: p for p in posts}
    require(len(by_id) == len(posts) and len({p['uri'] for p in posts}) == len(posts), 'Duplicate corpus records.')
    require(all(p['uri'].startswith(f'at://{did}/app.bsky.feed.post/') for p in posts), 'Corpus contains another author.')
    trait = next((t for t in estimate.get('interpretations', []) if t.get('dimension') == 'open_mindedness'), {})
    ids = trait.get('evidence_ids', []) if trait.get('estimate') else []
    require(len(set(ids)) == len(ids) and all(i in by_id for i in ids), 'Profile uses unknown or duplicate evidence.')
    declared = {p['id']: p for p in estimate.get('evidence', [])}
    for i in ids:
        require(i in declared and all(declared[i].get(k) == by_id[i].get(k) for k in ('text', 'url', 'date')),
                'Profile evidence differs from the frozen corpus.')
    preference = consent.get('confirmed_preference')
    require(preference is None or (isinstance(preference, dict)
            and preference.get('pattern') == 'testable_experiment'
            and isinstance(preference.get('quote'), str) and len(preference['quote'].strip()) >= 8),
            'Unsupported preference or missing participant feedback.')
    supported = len(ids) >= 2
    personalized = supported or preference is not None
    baseline = (f'{name}, zvu tě k technickému testu AI amplifikátorů. Porovnáme jeden účet se třemi při stejném počtu příspěvků. '
                'Změříme cenu, lidskou práci a odezvu mimo vlastní síť. Zveřejníme i nulový výsledek.')
    adapted = (f'{name}, co tu tezi o levných AI amplifikátorech vystavit testu? Jeden účet proti třem, stejný počet příspěvků. '
               'Změřme cenu, lidskou práci a odezvu mimo vlastní síť. Zveřejněme i nulový výsledek.') if personalized else baseline
    trace = [{'field': 'communication_pattern', 'before': 'zvu tě k technickému testu AI amplifikátorů',
              'after': 'co tu tezi o levných AI amplifikátorech vystavit testu',
              'reason': 'Konkrétní otevřená výzva k ověření; oporu tvoří uvedené doklady a případná přímá preference účastníka.'}] if personalized else []
    require(max(len(baseline), len(adapted)) + len('[BotyLab · AI · V3] ') <= 300, 'Invitation exceeds the labelled post length.')
    return {'kind': ORIGIN, 'scope': SCOPE, 'template_id': TEMPLATE_ID,
            'participant': {k: consent[k] for k in ('participant_name', 'participant_handle', 'participant_did', 'salutation')},
            'consent_statements': {k: consent[k] for k in ('profile_permission_quote', 'invitation_permission_quote')},
            'pattern': 'testable_experiment' if personalized else 'neutral_invitation',
            'selection_basis': (['profile_hypothesis'] if supported else []) + (['participant_confirmed_preference'] if preference else []),
            'profile_hypothesis': 'Zájem o nové možnosti, vlastní experimenty a ověřitelné výsledky.' if supported else None,
            'used_profile_dimensions': ['open_mindedness'] if supported else [],
            'evidence': [{k: by_id[i][k] for k in ('id', 'text', 'date', 'url')} for i in ids] if supported else [],
            'confirmed_preference': preference,
            'corpus': estimate['corpus'], 'profile_validated': False,
            'baseline': baseline, 'adapted': adapted, 'trace': trace,
            'effect_measured': False, 'public_target': None}


def make_case(inputs, topic, timestamp):
    invitation = derive(inputs)
    participant = invitation['participant']
    key = hashlib.sha256(participant['participant_did'].encode()).hexdigest()[:12]
    uri = f'sim://local-participant-invitations/{key}/request'
    prompt = 'Účastník požádal o místní ukázku oslovení k technickému experimentu s AI amplifikátory.'
    target = {'id': 'INVITE-' + key, 'uri': uri, 'root_uri': uri, 'cid': 'local:invitation:' + key,
              'author_did': participant['participant_did'], 'handle': participant['participant_handle'],
              'url': None, 'date': timestamp, 'text': prompt, 'origin': ORIGIN,
              'external_summary': '', 'links': []}
    source_text = 'Technický experiment: porovnat jeden účet se třemi při stejném počtu příspěvků; měřit cenu, lidskou práci a odezvu mimo vlastní síť; zveřejnit i nulový výsledek.'
    source = {'title': 'Zadání technické pozvánky', 'url': None, 'attachment_url': None,
              'text_kind': 'invitation_brief', 'language': 'cs', 'paragraphs': [{'id': 'S001', 'text': source_text}]}
    plan = {'topic': topic, 'intent': 'support_factual_contribution', 'synthetic_reactions': [],
            'jobs': [{'candidate_id': target['id'], 'decision': 'reply', 'role': 'explanation', 'language': 'cs',
                      'reason': 'Souhlasící účastník schválil ukázku technického oslovení; jde o místní pozvánku.',
                      'support_basis': invitation['profile_hypothesis'] or 'Neutrální technická pozvánka.',
                      'draft_body': invitation['adapted'], 'baseline_draft_body': invitation['baseline'],
                      'adaptation_trace': invitation['trace'], 'participant_invitation': invitation,
                      'context_evidence': [{'post_uri': uri, 'quote': prompt}],
                      'source_evidence': [{'paragraph_id': 'S001', 'quote': 'porovnat jeden účet se třemi při stejném počtu příspěvků'}]}],
            'limitations': ['Místní pozvánka pro souhlasícího účastníka, nikoli komentář pod veřejným příspěvkem.',
                           'Pozvánku skládá místní šablona z dříve schválené formulace. Tento krok neprovádí novou analýzu osobnosti ani nevolá jazykový model.',
                           'Použitý odhad je neověřená interpretace veřejného projevu; ostatní osobnostní dimenze se k formulaci nepoužívají.',
                           'Přímé schválení stylu je vedeno zvlášť od profilové hypotézy a nedokazuje účinnost oslovení.',
                           'Dva virtuální účty nemají úkol; jednomu příjemci se nepřipravují tři totožná oslovení.']}
    return {'source': source, 'candidates': {'context_origin': ORIGIN, 'candidates': [target]},
            'contexts': {target['id']: {'valid': True, 'posts': [target], 'scope': 'Local participant request; not an observed Bluesky post.'}},
            'invitation_context': inputs, 'plan': plan}


def validate_job(item, target, context, research):
    require(research['candidates'].get('context_origin') == ORIGIN, 'Participant invitation cannot target a public thread.')
    expected = derive(research['invitation_context'])
    require(item.get('participant_invitation') == expected, 'Invitation context differs from its evidence-backed derivation.')
    require(item['draft_body'] == expected['adapted'] and item.get('baseline_draft_body') == expected['baseline']
            and item.get('adaptation_trace') == expected['trace'], 'Only the scoped technical invitation templates are supported.')
    require(target['author_did'] == expected['participant']['participant_did']
            and target['handle'] == expected['participant']['participant_handle'], 'Invitation belongs to another recipient.')
    for post in context['posts']:
        require(post.get('origin') == ORIGIN and post['uri'].startswith('sim://local-participant-invitations/')
                and post['root_uri'] == post['uri'] and post['url'] is None,
                'Private participant invitations cannot be attached to public posts.')
