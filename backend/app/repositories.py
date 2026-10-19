from datetime import datetime, timezone

from pymongo import ReturnDocument

from .errors import BusinessError


def utcnow():
    return datetime.now(timezone.utc)


class SurveyRepository:
    def __init__(self, db):
        self.db = db

    async def owned(self, survey_id, user_id):
        survey = await self.db.surveys.find_one({'_id': survey_id, 'owner_id': user_id})
        if not survey:
            raise BusinessError('NOT_FOUND', '问卷不存在', 404)
        return survey

    async def public(self, code):
        survey = await self.db.surveys.find_one({'public_code': code, 'status': {'$ne': 'draft'}})
        if not survey:
            raise BusinessError('NOT_FOUND', '问卷不存在或尚未发布', 404)
        return survey

    async def update(self, survey_id, user_id, revision, values, status=None):
        query = {'_id': survey_id, 'owner_id': user_id, 'revision': revision}
        if status:
            query['status'] = status
        result = await self.db.surveys.find_one_and_update(
            query, {'$set': {**values, 'updated_at': utcnow()}, '$inc': {'revision': 1}},
            return_document=ReturnDocument.AFTER)
        if not result:
            raise BusinessError('REVISION_CONFLICT', '问卷已被修改或状态已变化，请重新加载后再操作', 409)
        return result


class ResponseRepository:
    def __init__(self, db):
        self.db = db

    async def aggregate(self, survey):
        single_ids = [q['id'] for q in survey['questions'] if q['type'] == 'single_choice']
        multi_ids = [q['id'] for q in survey['questions'] if q['type'] == 'multiple_choice']
        choice_group = {'$group': {'_id': {'qid': '$answers.question_id', 'value': '$answers.value'},
                                    'count': {'$sum': 1}}}
        pipeline = [
            {'$match': {'survey_id': survey['_id']}},
            {'$facet': {
                'total': [{'$count': 'value'}],
                'reached': [{'$unwind': '$visited_question_ids'},
                            {'$group': {'_id': '$visited_question_ids', 'count': {'$sum': 1}}}],
                'answered': [{'$unwind': '$answers'},
                             {'$group': {'_id': '$answers.question_id', 'count': {'$sum': 1},
                                         'average': {'$avg': '$answers.value'}}}],
                'single': [{'$unwind': '$answers'},
                           {'$match': {'answers.question_id': {'$in': single_ids}}}, choice_group],
                'multiple': [{'$unwind': '$answers'},
                             {'$match': {'answers.question_id': {'$in': multi_ids}}},
                             {'$unwind': '$answers.value'}, choice_group],
            }},
        ]
        result = (await (await self.db.responses.aggregate(pipeline)).to_list(1))[0]
        total = result['total'][0]['value'] if result['total'] else 0
        reached = {row['_id']: row['count'] for row in result['reached']}
        answered = {row['_id']: row for row in result['answered']}
        choices = {(row['_id']['qid'], row['_id']['value']): row['count']
                   for row in result['single'] + result['multiple']}
        questions = []
        for q in survey['questions']:
            qid = q['id']
            count, reach = answered.get(qid, {}).get('count', 0), reached.get(qid, 0)
            options = []
            for option in q['options']:
                value = choices.get((qid, option['id']), 0)
                options.append({**option, 'count': value,
                                'percentage': round(value / count * 100, 1) if count else 0})
            questions.append({'question_id': qid, 'title': q['title'], 'type': q['type'],
                              'answered_count': count, 'reached_count': reach,
                              'skipped_count': total - reach, 'unanswered_count': reach - count,
                              'average': answered.get(qid, {}).get('average') if q['type'] == 'number' else None,
                              'options': options})
        return {'total_responses': total, 'questions': questions}

