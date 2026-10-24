from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request

from .auth import current_user
from .errors import BusinessError
from .library import Library, public
from .library_schemas import (BankInput, BankList, BankOut, BankUpdate, ForkInput, LibraryCreate,
    LibraryQuestionList, LibraryQuestionOut, LibraryStatistics, LibraryUpdate, RestoreInput,
    ShareInput, SharesOut, UsageList, VersionCreate, VersionList, VersionOut)
from .library_statistics import statistics
from .repositories import utcnow
from .schemas import RevisionInput

router = APIRouter(prefix='/api', tags=['question-library'])
User = Annotated[dict, Depends(current_user)]
Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=100)]


@router.get('/question-banks', response_model=BankList)
async def banks(request: Request, user: User, archived: bool = False):
    return {'items': [public(doc, BankOut) async for doc in request.app.state.db.question_banks.find(
        {'owner_id': user['_id'], 'archived': archived}).sort('created_at', 1)]}


@router.post('/question-banks', response_model=BankOut, status_code=201)
async def create_bank(data: BankInput, request: Request, user: User):
    if not data.name.strip():
        raise BusinessError('EMPTY_NAME', '题库名称不能为空')
    now = utcnow()
    doc = data.model_dump() | {'_id': uuid4().hex, 'owner_id': user['_id'], 'archived': False,
                               'revision': 1, 'created_at': now, 'updated_at': now}
    await request.app.state.db.question_banks.insert_one(doc)
    return public(doc, BankOut)


@router.patch('/question-banks/{bid}', response_model=BankOut)
async def update_bank(bid: str, data: BankUpdate, request: Request, user: User):
    lib = Library(request.app.state.db, user)
    await lib.bank(bid)
    values = data.model_dump(exclude={'expected_revision'}, exclude_none=True)
    if 'name' in values and not values['name'].strip():
        raise BusinessError('EMPTY_NAME', '题库名称不能为空')
    result = await lib.db.question_banks.update_one({'_id': bid, 'revision': data.expected_revision},
        {'$set': values | {'updated_at': utcnow()}, '$inc': {'revision': 1}})
    if not result.matched_count:
        raise BusinessError('REVISION_CONFLICT', '题库已被修改，请刷新后重试', 409)
    return public(await lib.bank(bid), BankOut)


@router.get('/questions', response_model=LibraryQuestionList)
async def questions(request: Request, user: User, scope: Literal['mine', 'shared', 'used'] = 'mine',
                    bank_id: str | None = None, q: str = Query('', max_length=200),
                    kind: Literal['single_choice', 'multiple_choice', 'text', 'number'] | None = None,
                    archived: bool = False, page: Page = 1, page_size: Size = 20):
    return await Library(request.app.state.db, user).list_questions(scope, bank_id, q, kind, archived, page, page_size)


@router.post('/questions', response_model=LibraryQuestionOut, status_code=201)
async def create_question(data: LibraryCreate, request: Request, user: User):
    return await Library(request.app.state.db, user).create(data)


@router.get('/questions/{qid}', response_model=LibraryQuestionOut)
async def question(qid: str, request: Request, user: User):
    return await Library(request.app.state.db, user).output(qid)


@router.patch('/questions/{qid}', response_model=LibraryQuestionOut)
async def update_question(qid: str, data: LibraryUpdate, request: Request, user: User):
    lib = Library(request.app.state.db, user)
    await lib.owned(qid)
    values = data.model_dump(exclude={'expected_revision'}, exclude_none=True)
    if data.bank_id:
        await lib.bank(data.bank_id, True)
    result = await lib.db.questions.update_one({'_id': qid, 'revision': data.expected_revision},
        {'$set': values | {'updated_at': utcnow()}, '$inc': {'revision': 1}})
    if not result.matched_count:
        raise BusinessError('REVISION_CONFLICT', '题目已被修改，请刷新后重试', 409)
    return await lib.output(qid)


@router.get('/questions/{qid}/versions', response_model=VersionList)
async def versions(qid: str, request: Request, user: User, page: Page = 1, page_size: Size = 20):
    lib = Library(request.app.state.db, user)
    _, history, _ = await lib.readable(qid)
    query = {'question_id': qid}
    if history is not None:
        query['_id'] = {'$in': list(history)}
    return {'items': [public(doc, VersionOut) async for doc in lib.db.question_versions.find(query).sort(
        'version_no', -1).skip((page-1)*page_size).limit(page_size)],
        'total': await lib.db.question_versions.count_documents(query), 'page': page, 'page_size': page_size}


@router.get('/questions/{qid}/versions/{vid}', response_model=VersionOut)
async def version(qid: str, vid: str, request: Request, user: User):
    return public(await Library(request.app.state.db, user).version(qid, vid), VersionOut)


@router.post('/questions/{qid}/versions', response_model=VersionOut, status_code=201)
async def create_version(qid: str, data: VersionCreate, request: Request, user: User):
    return await Library(request.app.state.db, user).new_version(qid, data)


@router.post('/questions/{qid}/restore', response_model=VersionOut, status_code=201)
async def restore(qid: str, data: RestoreInput, request: Request, user: User):
    return await Library(request.app.state.db, user).new_version(qid, data, True)


@router.post('/questions/{qid}/fork', response_model=LibraryQuestionOut, status_code=201)
async def fork(qid: str, data: ForkInput, request: Request, user: User):
    return await Library(request.app.state.db, user).create(data, {'question_id': qid, 'version_id': data.source_version_id})


@router.get('/questions/{qid}/shares', response_model=SharesOut)
async def shares(qid: str, request: Request, user: User):
    return await Library(request.app.state.db, user).shares(qid)


@router.post('/questions/{qid}/shares', response_model=SharesOut)
async def share(qid: str, data: ShareInput, request: Request, user: User):
    return await Library(request.app.state.db, user).share(qid, data)


@router.delete('/questions/{qid}/shares/{uid}', response_model=SharesOut)
async def revoke(qid: str, uid: str, data: RevisionInput, request: Request, user: User):
    return await Library(request.app.state.db, user).share(qid, data, uid)


@router.get('/questions/{qid}/usages', response_model=UsageList)
async def usages(qid: str, request: Request, user: User, page: Page = 1, page_size: Size = 20):
    items = await Library(request.app.state.db, user).usages(qid)
    return {'items': items[(page-1)*page_size:page*page_size], 'total': len(items), 'page': page, 'page_size': page_size}


@router.get('/questions/{qid}/statistics', response_model=LibraryStatistics)
async def cross_statistics(qid: str, request: Request, user: User, version_id: str | None = None,
                           survey_ids: Annotated[list[str] | None, Query(max_length=100)] = None,
                           page: Page = 1, page_size: Size = 20):
    return await statistics(Library(request.app.state.db, user), qid, version_id, survey_ids, page, page_size)
