import hashlib
import json
import secrets
from uuid import uuid4

from pymongo.errors import DuplicateKeyError

from .errors import BusinessError
from .logic import check_definition, evaluate
from .library import validate_sources
from .repositories import ResponseRepository, SurveyRepository, utcnow
from .schemas import Definition, FormOut, SurveyOut


def effective_status(survey):
    if survey['status'] == 'published' and survey.get('deadline') and survey['deadline'] <= utcnow():
        return 'expired'
    return survey['status']


def require_open(survey):
    if effective_status(survey) != 'published':
        raise BusinessError('SURVEY_UNAVAILABLE', '问卷已关闭或已截止，无法继续提交', 409)


def definition_of(survey):
    return Definition.model_validate({key: survey[key] for key in Definition.model_fields})


async def survey_out(db, survey):
    values = {key: survey[key] for key in SurveyOut.model_fields
              if key in survey and key not in ('id', 'effective_status', 'response_count')}
    return SurveyOut(**values, id=survey['_id'], effective_status=effective_status(survey),
                     response_count=await db.responses.count_documents({'survey_id': survey['_id']}))


async def form_out(db, survey, user):
    already = await db.responses.find_one({'survey_id': survey['_id'], 'respondent_id': user['_id']}, {'_id': 1})
    return FormOut(**definition_of(survey).model_dump(), public_code=survey['public_code'],
                   definition_version=survey['definition_version'], deadline=survey.get('deadline'),
                   effective_status=effective_status(survey), already_submitted=bool(already))


class SurveyService:
    def __init__(self, db):
        self.db, self.repo = db, SurveyRepository(db)

    async def create(self, definition, user):
        await validate_sources(self.db, definition, user)
        now = utcnow()
        survey = {**definition.model_dump(), '_id': uuid4().hex, 'owner_id': user['_id'],
                  'public_code': secrets.token_urlsafe(16), 'status': 'draft', 'deadline': None,
                  'revision': 1, 'definition_version': 1, 'schema_version': 2,
                  'created_at': now, 'updated_at': now}
        await self.db.surveys.insert_one(survey)
        return await survey_out(self.db, survey)

    async def save(self, survey_id, data, user):
        survey = await self.repo.owned(survey_id, user['_id'])
        if survey['status'] != 'draft':
            raise BusinessError('DEFINITION_FROZEN', '已发布的问卷不能修改题目和填写设置', 409)
        if survey['revision'] != data.expected_revision:
            raise BusinessError('REVISION_CONFLICT', '问卷已被修改或状态已变化，请重新加载后再操作', 409)
        await validate_sources(self.db, data, user, survey)
        values = data.model_dump(exclude={'expected_revision'})
        ids = [q['id'] for q in values['questions']]
        if len(set(ids)) != len(ids) or {'NEXT', 'END'} & set(ids):
            raise BusinessError('DUPLICATE_ID', '题目 ID 必须唯一，且不能使用保留名称')
        for q in values['questions']:
            options = [o['id'] for o in q['options']]
            if len(set(options)) != len(options):
                raise BusinessError('DUPLICATE_ID', '选项 ID 不能重复', question_id=q['id'])
        survey = await self.repo.update(survey_id, user['_id'], data.expected_revision, values, 'draft')
        return await survey_out(self.db, survey)

    async def publish(self, survey_id, data, user):
        survey = await self.repo.owned(survey_id, user['_id'])
        result = check_definition(definition_of(survey))
        if not result.valid:
            first = result.errors[0]
            raise BusinessError(first.code, first.message, question_id=first.question_id)
        if survey.get('deadline') and survey['deadline'] <= utcnow():
            raise BusinessError('PAST_DEADLINE', '请先将截止时间设置为未来时间')
        survey = await self.repo.update(survey_id, user['_id'], data.expected_revision, {'status': 'published'}, 'draft')
        return await survey_out(self.db, survey)


def payload_hash(submission, normalized):
    payload = {'definition_version': submission.definition_version, 'is_anonymous': submission.is_anonymous,
               'answers': normalized}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


async def submit(db, survey, submission, user):
    query = {'survey_id': survey['_id'], 'respondent_id': user['_id'], 'request_id': submission.request_id}
    # Replays are considered before closed/deadline/repeat checks.
    existing = await db.responses.find_one(query)
    if not existing:
        require_open(survey)
    if submission.definition_version != survey['definition_version']:
        raise BusinessError('VERSION_MISMATCH', '问卷版本不一致，请重新打开问卷', 409)
    if submission.is_anonymous and not survey['settings']['allow_anonymous']:
        raise BusinessError('ANONYMITY_DISABLED', '该问卷不允许匿名填写')
    normalized, visited, _ = evaluate(definition_of(survey), submission.answers)
    digest = payload_hash(submission, normalized)

    def receipt(document, replayed):
        if document['payload_hash'] != digest:
            raise BusinessError('IDEMPOTENCY_CONFLICT', '同一提交编号不能用于不同答案，请重新开始填写', 409)
        return {'id': document['_id'], 'submitted_at': document['submitted_at'], 'replayed': replayed}

    if existing:
        return receipt(existing, True)
    # Definition is immutable; only lifecycle/deadline needs a final read.
    latest = await db.surveys.find_one({'_id': survey['_id']})
    require_open(latest)
    accepted_at = utcnow()
    if latest.get('deadline') and latest['deadline'] <= accepted_at:
        raise BusinessError('SURVEY_UNAVAILABLE', '问卷已截止', 409)
    document = {'_id': uuid4().hex, **query, 'definition_version': survey['definition_version'],
                'schema_version': 1, 'is_anonymous': submission.is_anonymous,
                'single_submission': not survey['settings']['allow_multiple'],
                'answers': normalized, 'visited_question_ids': visited,
                'payload_hash': digest, 'submitted_at': accepted_at}
    try:
        await db.responses.insert_one(document)
    except DuplicateKeyError:
        existing = await db.responses.find_one(query)
        if existing:
            return receipt(existing, True)
        raise BusinessError('ALREADY_SUBMITTED', '你已填写过这份问卷，不能重复提交', 409)
    return receipt(document, False)


async def response_out(db, document):
    # Explicit allowlist: never return respondent_id, request_id, payload_hash.
    respondent = None
    if not document['is_anonymous']:
        user = await db.users.find_one({'_id': document['respondent_id']}, {'username': 1})
        respondent = user['username'] if user else '已注销用户'
    return {'id': document['_id'], 'definition_version': document['definition_version'],
            'is_anonymous': document['is_anonymous'], 'respondent': respondent,
            'answers': document['answers'], 'visited_question_ids': document['visited_question_ids'],
            'submitted_at': document['submitted_at']}
