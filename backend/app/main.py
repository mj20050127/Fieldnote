import json
import logging
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from starlette.concurrency import run_in_threadpool

from .auth import (DUMMY_HASH, create_session, current_user, password_hasher,
                   token_hash, username_key, verify_password)
from .config import ROOT, Settings
from .database import initialize_database
from .errors import BusinessError
from .examples import soccer_definition
from .logic import check_definition, evaluate
from .middleware import BodyLimitMiddleware
from .repositories import ResponseRepository, SurveyRepository, utcnow
from .schemas import (Credentials, Definition, DefinitionCheck, DraftUpdate, EvaluateInput,
                      EvaluateOut, FormOut, ManagementUpdate, Overview, QuestionStatistics, Receipt,
                      ResponseList, ResponseOut, RevisionInput, Statistics, Submission,
                      SurveyList, SurveyOut, UserMe)
from .services import (SurveyService, definition_of, form_out, require_open,
                       response_out, submit, survey_out)

logger = logging.getLogger('fieldnote')
User = Annotated[dict, Depends(current_user)]


def create_app(settings: Settings | None = None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        client = AsyncMongoClient(settings.mongo_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        app.state.db = client[settings.mongo_database]
        try:
            await client.admin.command('ping')
            await initialize_database(app.state.db)
            yield
        finally:
            await client.close()

    app = FastAPI(title='Fieldnote 问卷 API', version='1.0.0', lifespan=lifespan,
                  docs_url='/api/docs', openapi_url='/api/openapi.json', redoc_url=None)
    app.state.settings = settings
    attempts = defaultdict(deque)

    @app.exception_handler(BusinessError)
    async def business_error(request, error):
        return JSONResponse(status_code=error.status, content={'error': {
            'code': error.code, 'message': error.message,
            'question_id': error.question_id, 'field': error.field}})

    @app.exception_handler(RequestValidationError)
    async def request_error(request, error):
        # Never echo request bodies or passwords into validation errors.
        first = error.errors()[0]
        return JSONResponse(status_code=422, content={'error': {
            'code': 'INVALID_REQUEST', 'message': first['msg'],
            'field': '.'.join(str(part) for part in first['loc']), 'question_id': None}})

    @app.middleware('http')
    async def security(request, call_next):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if origin and origin.rstrip('/') not in settings.allowed_origins:
                return JSONResponse({'error': {'code': 'ORIGIN_DENIED', 'message': '请求来源不被允许'}}, status_code=403)
            declared = request.headers.get('content-length')
            if declared and (not declared.isdecimal() or int(declared) > 1024 * 1024):
                return JSONResponse({'error': {'code': 'BODY_TOO_LARGE', 'message': '请求不能超过 1 MiB'}}, status_code=413)
        if settings.app_env != 'test' and request.url.path in ('/api/auth/login', '/api/auth/register'):
            now = time.monotonic()
            # Bound limiter memory; it is transient protection, not business data.
            if len(attempts) > 10000:
                for key in list(attempts):
                    if not attempts[key] or attempts[key][-1] < now - 60:
                        del attempts[key]
            key = request.client.host if request.client else 'unknown'
            history = attempts[key]
            while history and history[0] < now - 60:
                history.popleft()
            if len(history) >= 20:
                return JSONResponse({'error': {'code': 'RATE_LIMITED', 'message': '操作太频繁，请一分钟后重试'}},
                                    status_code=429, headers={'Retry-After': '60'})
            history.append(now)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/health')
    async def health(request: Request):
        try:
            await request.app.state.db.command('ping')
            return {'status': 'ok', 'database': 'connected'}
        except PyMongoError:
            return JSONResponse({'status': 'unavailable'}, status_code=503)

    @app.post('/api/auth/register', response_model=UserMe, status_code=201)
    async def register(data: Credentials, request: Request, response: Response):
        username, key = username_key(data.username)
        user = {'_id': uuid4().hex, 'username': username, 'username_key': key,
                'password_hash': await run_in_threadpool(password_hasher.hash, data.password), 'created_at': utcnow()}
        try:
            await request.app.state.db.users.insert_one(user)
        except DuplicateKeyError:
            raise BusinessError('USERNAME_TAKEN', '这个用户名已被使用', 409, field='username')
        return await create_session(request, response, user)

    @app.post('/api/auth/login', response_model=UserMe)
    async def login(data: Credentials, request: Request, response: Response):
        _, key = username_key(data.username)
        db = request.app.state.db
        user = await db.users.find_one({'username_key': key})
        valid = await verify_password(data.password, user['password_hash'] if user else DUMMY_HASH)
        if not user or not valid:
            raise BusinessError('INVALID_CREDENTIALS', '用户名或密码错误', 401)
        old = request.cookies.get(settings.cookie_name)
        if old:
            await db.sessions.delete_one({'_id': token_hash(old)})
        return await create_session(request, response, user)

    @app.get('/api/auth/me', response_model=UserMe)
    async def me(request: Request, user: User):
        return {'id': user['_id'], 'username': user['username'], 'csrf_token': request.state.session['csrf_token']}

    @app.post('/api/auth/logout', status_code=204)
    async def logout(request: Request, response: Response, user: User):
        await request.app.state.db.sessions.delete_one({'_id': request.state.session['_id']})
        response.delete_cookie(settings.cookie_name, path='/', secure=settings.production, httponly=True, samesite='lax')

    @app.get('/api/templates/soccer', response_model=Definition)
    async def template(user: User):
        return soccer_definition()

    @app.get('/api/overview', response_model=Overview)
    async def overview(request: Request, user: User):
        db = request.app.state.db
        pipeline = [
            {'$match': {'owner_id': user['_id']}},
            {'$lookup': {'from': 'responses', 'let': {'sid': '$_id'}, 'pipeline': [
                {'$match': {'$expr': {'$eq': ['$survey_id', '$$sid']}}}, {'$count': 'value'}], 'as': 'response_total'}},
            {'$group': {'_id': None, 'total_surveys': {'$sum': 1},
                        'total_responses': {'$sum': {'$ifNull': [{'$arrayElemAt': ['$response_total.value', 0]}, 0]}},
                        'draft': {'$sum': {'$cond': [{'$eq': ['$status', 'draft']}, 1, 0]}},
                        'published': {'$sum': {'$cond': [{'$and': [
                            {'$eq': ['$status', 'published']},
                            {'$or': [{'$eq': ['$deadline', None]}, {'$gt': ['$deadline', utcnow()]}]}]}, 1, 0]}}}},
        ]
        rows = await (await db.surveys.aggregate(pipeline)).to_list(1)
        if not rows:
            return {'total_surveys': 0, 'total_responses': 0, 'published': 0, 'draft': 0}
        return {key: value for key, value in rows[0].items() if key != '_id'}

    @app.get('/api/surveys', response_model=SurveyList)
    async def surveys(request: Request, user: User, page: int = Query(1, ge=1),
                      page_size: int = Query(12, ge=1, le=100),
                      status: Literal['draft', 'published', 'closed', 'expired'] | None = None,
                      q: str = Query('', max_length=120)):
        db = request.app.state.db
        query = {'owner_id': user['_id']}
        if q.strip():
            query['title'] = {'$regex': re.escape(q.strip()), '$options': 'i'}
        if status == 'expired':
            query.update(status='published', deadline={'$ne': None, '$lte': utcnow()})
        elif status == 'published':
            query.update(status='published')
            query['$or'] = [{'deadline': None}, {'deadline': {'$gt': utcnow()}}]
        elif status:
            query['status'] = status
        documents = await db.surveys.find(query).sort('created_at', -1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
        return {'items': [await survey_out(db, doc) for doc in documents],
                'total': await db.surveys.count_documents(query), 'page': page, 'page_size': page_size}

    @app.post('/api/surveys', response_model=SurveyOut, status_code=201)
    async def create(data: Definition, request: Request, user: User):
        return await SurveyService(request.app.state.db).create(data, user)

    @app.get('/api/surveys/{survey_id}', response_model=SurveyOut)
    async def detail(survey_id: str, request: Request, user: User):
        db = request.app.state.db
        return await survey_out(db, await SurveyRepository(db).owned(survey_id, user['_id']))

    @app.put('/api/surveys/{survey_id}/definition', response_model=SurveyOut)
    async def save(survey_id: str, data: DraftUpdate, request: Request, user: User):
        return await SurveyService(request.app.state.db).save(survey_id, data, user)

    @app.patch('/api/surveys/{survey_id}', response_model=SurveyOut)
    async def manage(survey_id: str, data: ManagementUpdate, request: Request, user: User):
        db = request.app.state.db
        await SurveyRepository(db).owned(survey_id, user['_id'])
        if data.deadline and data.deadline <= utcnow():
            raise BusinessError('PAST_DEADLINE', '截止时间应晚于当前时间')
        survey = await SurveyRepository(db).update(survey_id, user['_id'], data.expected_revision, {'deadline': data.deadline})
        return await survey_out(db, survey)

    @app.post('/api/surveys/{survey_id}/validate', response_model=DefinitionCheck)
    async def validate(survey_id: str, request: Request, user: User):
        survey = await SurveyRepository(request.app.state.db).owned(survey_id, user['_id'])
        return check_definition(definition_of(survey))

    @app.post('/api/surveys/{survey_id}/publish', response_model=SurveyOut)
    async def publish(survey_id: str, data: RevisionInput, request: Request, user: User):
        return await SurveyService(request.app.state.db).publish(survey_id, data, user)

    @app.post('/api/surveys/{survey_id}/close', response_model=SurveyOut)
    async def close(survey_id: str, data: RevisionInput, request: Request, user: User):
        db = request.app.state.db
        survey = await SurveyRepository(db).owned(survey_id, user['_id'])
        if survey['status'] == 'closed':
            return await survey_out(db, survey)
        if survey['status'] != 'published':
            raise BusinessError('NOT_PUBLISHED', '只有已发布的问卷可以关闭', 409)
        survey = await SurveyRepository(db).update(survey_id, user['_id'], data.expected_revision, {'status': 'closed'}, 'published')
        return await survey_out(db, survey)

    @app.post('/api/surveys/{survey_id}/preview', response_model=EvaluateOut)
    async def preview(survey_id: str, data: EvaluateInput, request: Request, user: User):
        survey = await SurveyRepository(request.app.state.db).owned(survey_id, user['_id'])
        definition = definition_of(survey)
        check = check_definition(definition)
        if not check.valid:
            issue = check.errors[0]
            raise BusinessError(issue.code, issue.message, question_id=issue.question_id)
        _, visited, target = evaluate(definition, data.answers, data.current_question_id)
        return {'visited_question_ids': visited, 'next_question_id': target}

    @app.get('/api/forms/{code}', response_model=FormOut)
    async def form(code: str, request: Request, user: User):
        db = request.app.state.db
        return await form_out(db, await SurveyRepository(db).public(code), user)

    @app.post('/api/forms/{code}/next', response_model=EvaluateOut)
    async def advance(code: str, data: EvaluateInput, request: Request, user: User):
        survey = await SurveyRepository(request.app.state.db).public(code)
        require_open(survey)
        _, visited, target = evaluate(definition_of(survey), data.answers, data.current_question_id)
        return {'visited_question_ids': visited, 'next_question_id': target}

    @app.post('/api/forms/{code}/responses', response_model=Receipt, status_code=201)
    async def respond(code: str, data: Submission, request: Request, response: Response, user: User):
        db = request.app.state.db
        survey = await SurveyRepository(db).public(code)
        receipt = await submit(db, survey, data, user)
        if receipt['replayed']:
            response.status_code = 200
        return receipt

    @app.get('/api/surveys/{survey_id}/statistics', response_model=Statistics)
    async def statistics(survey_id: str, request: Request, user: User):
        db = request.app.state.db
        survey = await SurveyRepository(db).owned(survey_id, user['_id'])
        return await ResponseRepository(db).aggregate(survey)

    @app.get('/api/surveys/{survey_id}/questions/{qid}/statistics', response_model=QuestionStatistics)
    async def question_statistics(survey_id: str, qid: str, request: Request, user: User,
                                  page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        db = request.app.state.db
        survey = await SurveyRepository(db).owned(survey_id, user['_id'])
        stats = await ResponseRepository(db).aggregate(survey)
        result = next((q for q in stats['questions'] if q['question_id'] == qid), None)
        if not result:
            raise BusinessError('NOT_FOUND', '题目不存在', 404)
        query = {'survey_id': survey_id, 'answers.question_id': qid}
        documents = await db.responses.find(query, {'answers': {'$elemMatch': {'question_id': qid}}, 'submitted_at': 1}).sort('submitted_at', -1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
        return {**result, 'values': [{'value': doc['answers'][0]['value'], 'submitted_at': doc['submitted_at']} for doc in documents],
                'total': result['answered_count'], 'page': page, 'page_size': page_size}

    @app.get('/api/surveys/{survey_id}/responses', response_model=ResponseList)
    async def responses(survey_id: str, request: Request, user: User,
                        page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        db = request.app.state.db
        await SurveyRepository(db).owned(survey_id, user['_id'])
        query = {'survey_id': survey_id}
        docs = await db.responses.find(query).sort('submitted_at', -1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
        return {'items': [await response_out(db, doc) for doc in docs],
                'total': await db.responses.count_documents(query), 'page': page, 'page_size': page_size}

    @app.get('/api/surveys/{survey_id}/responses/{response_id}', response_model=ResponseOut)
    async def response_detail(survey_id: str, response_id: str, request: Request, user: User):
        db = request.app.state.db
        await SurveyRepository(db).owned(survey_id, user['_id'])
        doc = await db.responses.find_one({'_id': response_id, 'survey_id': survey_id})
        if not doc:
            raise BusinessError('NOT_FOUND', '答卷不存在', 404)
        return await response_out(db, doc)

    @app.get('/api/{rest:path}', include_in_schema=False)
    async def unknown_api(rest: str):
        raise BusinessError('NOT_FOUND', '接口不存在', 404)

    dist = ROOT / 'frontend' / 'dist'

    @app.get('/{path:path}', include_in_schema=False)
    async def frontend(path: str):
        candidate = (dist / path).resolve()
        if dist.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        if (dist / 'index.html').is_file():
            return FileResponse(dist / 'index.html')
        return JSONResponse({'message': '前端尚未构建，请运行 npm run build 或使用 http://localhost:5173'}, status_code=404)

    app.add_middleware(BodyLimitMiddleware)
    return app


app = create_app()
