"""Small content-profile fixture shared by independent workflow tests."""


def profile_for(candidate, context, source, decision='reply'):
    anchor = next(p for p in context['posts'] if p['uri'] == candidate['uri'])
    quote = {'post_uri': anchor['uri'], 'quote': anchor['text']}
    return {'candidate_id': candidate['id'], 'topic': 'A public explanation of a supplier case',
            'main_question': 'Does the supplied case belong in this discussion?', 'language': 'en',
            'tone': {'label': 'factual', 'description': 'The post presents an explanation.', 'evidence': [quote]},
            'arguments': [{'summary': 'The author discusses the stated topic.', 'evidence': [quote]}],
            'already_covered': [{'summary': 'The anchor explanation is already present.', 'evidence': [quote]}],
            'open_questions': [],
            'contribution': {'decision': decision, 'criterion': 'thematic_fit',
                'reason': 'The case is thematically connected to the anchor.' if decision == 'reply' else 'The case concerns a different topic.',
                'connection': 'The reply discusses the same issue.' if decision == 'reply' else 'The supplied case concerns a different issue.',
                'reply_mode': 'support' if decision == 'reply' else None, 'added_value': None,
                'context_evidence': [quote],
                'source_evidence': ([{'paragraph_id': source['paragraphs'][0]['id'], 'quote': source['paragraphs'][0]['text']}]
                                    if source.get('paragraphs') and decision == 'reply' else [])},
            'limitations': ['This is a bounded fixture context, not a complete discussion.']}
