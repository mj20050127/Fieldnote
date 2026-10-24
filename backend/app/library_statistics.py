"""Owner-scoped MongoDB aggregation; each immutable version is a separate population."""
from .library import public
from .library_schemas import VersionOut


async def statistics(library, qid, version_id, survey_ids, page, page_size):
    usages = await library.usages(qid, survey_ids)
    versions = {slot['version_id'] for usage in usages for slot in usage['slots']}
    if version_id:
        await library.version(qid, version_id)
        versions = {version_id}
    if not versions:
        versions = {(await library.output(qid))['latest_version']['id']}
    groups = []
    for vid in versions:
        version = await library.version(qid, vid)
        refs = {u['survey_id']: [s['instance_id'] for s in u['slots'] if s['version_id'] == vid] for u in usages}
        refs = {sid: ids for sid, ids in refs.items() if ids}
        offset = (page - 1) * page_size
        facets = {
            'counts': [{'$group': {'_id': None, 'response_count': {'$sum': 1},
                        'occurrence_count': {'$sum': {'$size': '$slots'}},
                        'reached_count': {'$sum': {'$size': {'$setIntersection': ['$slots', '$visited_question_ids']}}},
                        'answered_count': {'$sum': {'$size': '$matched'}}}}],
            'numbers': [{'$unwind': '$matched'}, {'$group': {'_id': None, 'average': {'$avg': '$matched.value'},
                        'minimum': {'$min': '$matched.value'}, 'maximum': {'$max': '$matched.value'}}}],
            'values': [{'$sort': {'submitted_at': -1, '_id': 1}}, {'$unwind': '$matched'},
                       {'$skip': offset}, {'$limit': page_size}, {'$project': {'_id': 0, 'value': '$matched.value', 'submitted_at': 1}}],
        }
        kind = version['content']['type']
        if kind in ('single_choice', 'multiple_choice'):
            facets['choices'] = [{'$unwind': '$matched'}, {'$unwind': '$matched.value'},
                                 {'$group': {'_id': '$matched.value', 'count': {'$sum': 1}}}]
        if kind == 'number':
            grouped = [{'$unwind': '$matched'}, {'$group': {'_id': '$matched.value', 'count': {'$sum': 1}}}]
            facets['frequencies'] = grouped + [{'$sort': {'_id': 1}}, {'$skip': offset}, {'$limit': page_size}]
            facets['frequency_total'] = grouped + [{'$count': 'value'}]
        # $switch needs at least one branch, including when there are no usages yet.
        switch = {'branches': [{'case': {'$eq': ['$survey_id', sid]}, 'then': {'$literal': ids}}
                               for sid, ids in refs.items()] or [{'case': True, 'then': []}], 'default': []}
        pipeline = [{'$match': {'survey_id': {'$in': list(refs)}}}, {'$set': {'slots': {'$switch': switch}}},
                    {'$set': {'matched': {'$filter': {'input': '$answers', 'as': 'answer',
                              'cond': {'$in': ['$$answer.question_id', '$slots']}}}}}, {'$facet': facets}]
        result = (await (await library.db.responses.aggregate(pipeline)).to_list(1))[0]
        counts = result['counts'][0] if result['counts'] else dict.fromkeys(
            ['response_count', 'occurrence_count', 'reached_count', 'answered_count'], 0)
        counts.pop('_id', None)
        options = []
        choice_counts = {row['_id']: row['count'] for row in result.get('choices', [])}
        for option in version['content']['options']:
            count = choice_counts.get(option['id'], 0)
            options.append(option | {'count': count, 'percentage': round(count / counts['answered_count'] * 100, 2)
                                     if counts['answered_count'] else 0})
        numeric = result['numbers'][0] if kind == 'number' and result['numbers'] else {}
        groups.append({'version': public(version, VersionOut), 'survey_count': len(refs), **counts,
                       'skipped_count': counts['occurrence_count'] - counts['reached_count'],
                       'unanswered_count': counts['reached_count'] - counts['answered_count'],
                       **{key: numeric.get(key) for key in ['average', 'minimum', 'maximum']},
                       'options': options, 'values': result['values'],
                       'frequencies': [{'value': row['_id'], 'count': row['count']} for row in result.get('frequencies', [])],
                       'frequency_total': (result.get('frequency_total') or [{}])[0].get('value', 0),
                       'page': page, 'page_size': page_size})
    return {'question_id': qid, 'groups': sorted(groups, key=lambda group: group['version']['version_no'])}
