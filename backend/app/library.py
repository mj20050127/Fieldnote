"""Immutable question content and private, snapshot-based reuse. No transactions required."""
import hashlib
import json
import re
from uuid import NAMESPACE_URL, uuid5

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .auth import username_key
from .errors import BusinessError
from .logic import check_definition
from .repositories import utcnow
from .schemas import Definition, Question, QuestionContent


def stable_id(value):
    return uuid5(NAMESPACE_URL, 'fieldnote:' + value).hex


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def content_of(question):
    value = question.model_dump() if hasattr(question, 'model_dump') else question
    return QuestionContent.model_validate({key: value[key] for key in QuestionContent.model_fields
                                           if key in value}).model_dump()


def validate_content(content):
    result = check_definition(Definition(title='题库', questions=[Question(id='content', **content)]))
    if not result.valid:
        first = result.errors[0]
        raise BusinessError(first.code, first.message, field='content')


def public(document, model):
    return {key: document.get(key) for key in model.model_fields if key != 'id'} | {'id': document['_id']}


class Library:
    def __init__(self, db, user):
        self.db, self.user, self.uid = db, user, user['_id']

    async def bank(self, bank_id, usable=False):
        bank = await self.db.question_banks.find_one({'_id': bank_id, 'owner_id': self.uid})
        if not bank:
            raise BusinessError('NOT_FOUND', '题库不存在', 404)
        if usable and bank['archived']:
            raise BusinessError('ARCHIVED', '请先恢复已归档的题库', 409)
        return bank

    async def owned(self, qid, usable=False):
        doc = await self.db.questions.find_one({'_id': qid, 'owner_id': self.uid, 'status': 'active'})
        if not doc:
            raise BusinessError('NOT_FOUND', '题目不存在', 404)
        if usable:
            await self.bank(doc['bank_id'], True)
            if doc['archived']:
                raise BusinessError('ARCHIVED', '请先恢复已归档的题目', 409)
        return doc

    async def historical_versions(self, qid):
        result = set()
        async for survey in self.db.surveys.find({'owner_id': self.uid, 'questions.source.question_id': qid}, {'questions.source': 1}):
            result.update(q['source']['version_id'] for q in survey['questions']
                          if (q.get('source') or {}).get('question_id') == qid)
        return result

    async def readable(self, qid, reuse=False):
        doc = await self.db.questions.find_one({'_id': qid, 'status': 'active'})
        if not doc:
            raise BusinessError('NOT_FOUND', '题目不存在', 404)
        granted = doc['owner_id'] == self.uid or self.uid in doc['shared_with']
        history = None if granted else await self.historical_versions(qid)
        if not granted and (reuse or not history):
            raise BusinessError('NOT_FOUND', '题目不存在或使用授权已撤销', 404)
        bank = await self.db.question_banks.find_one({'_id': doc['bank_id']})
        available = granted and not doc['archived'] and bool(bank) and not bank['archived']
        if reuse and not available:
            raise BusinessError('ARCHIVED', '已归档的题目或题库不能新增引用', 409)
        return doc, history, available

    async def version(self, qid, vid, reuse=False):
        _, history, _ = await self.readable(qid, reuse)
        version = await self.db.question_versions.find_one({'_id': vid, 'question_id': qid})
        if not version or history is not None and vid not in history:
            raise BusinessError('NOT_FOUND', '题目版本不存在', 404)
        return version

    async def output(self, qid):
        from .library_schemas import VersionOut
        doc, history, available = await self.readable(qid)
        query = {'question_id': qid}
        if history is not None:
            query['_id'] = {'$in': list(history)}
        latest = await self.db.question_versions.find_one(query, sort=[('version_no', -1)])
        if not latest:
            raise BusinessError('NOT_FOUND', '题目尚未完成创建，请重试原请求', 404)
        owner = await self.db.users.find_one({'_id': doc['owner_id']}, {'username': 1})
        return {key: doc[key] for key in ['owner_id', 'bank_id', 'archived', 'revision', 'derived_from', 'created_at', 'updated_at']} | {
            'id': qid, 'owner_username': owner['username'] if owner else '已停用用户',
            'access': 'owner' if doc['owner_id'] == self.uid else 'shared' if history is None else 'historical',
            'available_for_reuse': available, 'latest_version': public(latest, VersionOut)}

    async def existing_operation(self, request_id, payload_hash, qid=None):
        version = await self.db.question_versions.find_one({'created_by': self.uid, 'request_id': request_id})
        if version and (version['payload_hash'] != payload_hash or qid and version['question_id'] != qid):
            raise BusinessError('REQUEST_CONFLICT', '同一请求编号不能用于不同内容', 409)
        return version

    async def create(self, data, source=None):
        content = data.content.model_dump()
        validate_content(content)
        payload_hash = digest({'action': 'fork' if source else 'create', 'bank': data.bank_id,
                               'content': content, 'source': source})
        qid = stable_id(f'create:{self.uid}:{data.request_id}')
        previous = await self.existing_operation(data.request_id, payload_hash, qid)
        # A completed idempotent operation remains replayable after subsequent archival/revocation.
        if previous:
            await self.db.questions.update_one({'_id': qid, 'status': 'creating'}, {'$set': {'status': 'active'}})
            return await self.output(qid)
        await self.bank(data.bank_id, True)
        if source:
            await self.version(source['question_id'], source['version_id'], True)
        now = utcnow()
        doc = {'_id': qid, 'owner_id': self.uid, 'bank_id': data.bank_id, 'shared_with': [],
               'version_counter': 1, 'revision': 1, 'status': 'creating', 'archived': False,
               'derived_from': source, 'creation_hash': payload_hash, 'created_at': now, 'updated_at': now}
        try:
            await self.db.questions.update_one({'_id': qid}, {'$setOnInsert': doc}, upsert=True)
        except DuplicateKeyError:
            pass
        saved = await self.db.questions.find_one({'_id': qid})
        if saved['creation_hash'] != payload_hash:
            raise BusinessError('REQUEST_CONFLICT', '同一请求编号不能用于不同内容', 409)
        version = {'_id': stable_id(f'version:{self.uid}:{data.request_id}'), 'question_id': qid,
                   'version_no': 1, 'parent_version_id': None, 'restored_from_version_id': None,
                   'content': content, 'created_by': self.uid, 'request_id': data.request_id,
                   'payload_hash': payload_hash, 'created_at': now}
        try:
            await self.db.question_versions.insert_one(version)
        except DuplicateKeyError:
            if not await self.existing_operation(data.request_id, payload_hash, qid):
                raise
        await self.db.questions.update_one({'_id': qid}, {'$set': {'status': 'active'}})
        return await self.output(qid)

    async def new_version(self, qid, data, restore=False):
        from .library_schemas import VersionOut
        # Include explicit parent in the hash so a retry cannot silently change its branch.
        payload = data.model_dump(exclude={'request_id'}) | {'action': 'restore' if restore else 'version', 'qid': qid}
        payload_hash = digest(payload)
        previous = await self.existing_operation(data.request_id, payload_hash, qid)
        if previous:
            await self.owned(qid)
            return public(previous, VersionOut)
        await self.owned(qid, True)
        await self.version(qid, data.parent_version_id)
        content = (await self.version(qid, data.target_version_id))['content'] if restore else data.content.model_dump()
        validate_content(content)
        doc = await self.db.questions.find_one_and_update({'_id': qid, 'owner_id': self.uid, 'archived': False},
                   {'$inc': {'version_counter': 1}, '$set': {'updated_at': utcnow()}}, return_document=ReturnDocument.AFTER)
        if not doc:
            raise BusinessError('ARCHIVED', '题目已归档', 409)
        version = {'_id': stable_id(f'version:{self.uid}:{data.request_id}'), 'question_id': qid,
                   'version_no': doc['version_counter'], 'parent_version_id': data.parent_version_id,
                   'restored_from_version_id': data.target_version_id if restore else None,
                   'content': content, 'created_by': self.uid, 'request_id': data.request_id,
                   'payload_hash': payload_hash, 'created_at': utcnow()}
        try:
            await self.db.question_versions.insert_one(version)
        except DuplicateKeyError:
            version = await self.existing_operation(data.request_id, payload_hash, qid)
            if not version:
                raise
        return public(version, VersionOut)

    async def list_questions(self, scope, bank_id, q, kind, archived, page, page_size):
        match = {'status': 'active', 'archived': archived}
        if scope == 'mine':
            match['owner_id'] = self.uid
            if bank_id:
                await self.bank(bank_id)
                match['bank_id'] = bank_id
        elif scope == 'shared':
            match.update({'shared_with': self.uid, 'owner_id': {'$ne': self.uid}})
        else:
            ids = await self.db.surveys.distinct('questions.source.question_id', {'owner_id': self.uid})
            match['_id'] = {'$in': [v for v in ids if v]}
        pipeline = [{'$match': match}, {'$lookup': {'from': 'question_versions', 'let': {'qid': '$_id'},
                    'pipeline': [{'$match': {'$expr': {'$eq': ['$question_id', '$$qid']}}},
                                 {'$sort': {'version_no': -1}}, {'$limit': 1}], 'as': 'latest'}},
                    {'$unwind': '$latest'}]
        # Historical list must not filter on an unauthorized new version's title/type.
        if scope == 'used':
            items = [await self.output(doc['_id']) async for doc in self.db.questions.find(match)]
            items = [v for v in items if (not q or q.casefold() in v['latest_version']['content']['title'].casefold())
                     and (not kind or v['latest_version']['content']['type'] == kind)]
            items.sort(key=lambda v: v['updated_at'], reverse=True)
            return {'items': items[(page-1)*page_size:page*page_size], 'total': len(items), 'page': page, 'page_size': page_size}
        filters = {}
        if q:
            filters['latest.content.title'] = {'$regex': re.escape(q), '$options': 'i'}
        if kind:
            filters['latest.content.type'] = kind
        pipeline += [{'$match': filters}, {'$sort': {'updated_at': -1, '_id': 1}}, {'$facet': {
            'items': [{'$skip': (page-1)*page_size}, {'$limit': page_size}, {'$project': {'_id': 1}}],
            'total': [{'$count': 'value'}]}}]
        result = (await (await self.db.questions.aggregate(pipeline)).to_list(1))[0]
        return {'items': [await self.output(doc['_id']) for doc in result['items']],
                'total': result['total'][0]['value'] if result['total'] else 0, 'page': page, 'page_size': page_size}

    async def usages(self, qid, survey_ids=None):
        await self.readable(qid)
        query = {'owner_id': self.uid, 'questions.source.question_id': qid}
        if survey_ids is not None:
            query['_id'] = {'$in': survey_ids}
        return [{'survey_id': doc['_id'], 'title': doc['title'], 'status': doc['status'],
                 'slots': [{'instance_id': q['id'], 'version_id': q['source']['version_id']} for q in doc['questions']
                           if q.get('source') and q['source']['question_id'] == qid]}
                async for doc in self.db.surveys.find(query).sort('created_at', -1)]

    async def share(self, qid, data, remove=None):
        doc = await self.owned(qid)
        if remove:
            change = {'$pull': {'shared_with': remove}}
        else:
            _, key = username_key(data.username)
            recipient = await self.db.users.find_one({'username_key': key})
            if not recipient:
                raise BusinessError('NOT_FOUND', '找不到这个用户名', 404)
            if recipient['_id'] == self.uid:
                raise BusinessError('INVALID_SHARE', '无需向自己共享')
            if len(doc['shared_with']) >= 100 and recipient['_id'] not in doc['shared_with']:
                raise BusinessError('SHARE_LIMIT', '单题最多向 100 个用户共享')
            change = {'$addToSet': {'shared_with': recipient['_id']}}
        result = await self.db.questions.update_one({'_id': qid, 'revision': data.expected_revision},
                    change | {'$inc': {'revision': 1}, '$set': {'updated_at': utcnow()}})
        if not result.matched_count:
            raise BusinessError('REVISION_CONFLICT', '题目已被修改，请刷新后重试', 409)
        return await self.shares(qid)

    async def shares(self, qid):
        doc = await self.owned(qid)
        return {'revision': doc['revision'], 'items': [{'id': row['_id'], 'username': row['username']}
                async for row in self.db.users.find({'_id': {'$in': doc['shared_with']}}, {'username': 1})]}


async def validate_sources(db, definition, user, existing=None):
    library = Library(db, user)
    old = {q['id']: q for q in existing['questions']} if existing else {}
    for question in definition.questions:
        previous = old.get(question.id, {})
        if not question.source:
            if previous.get('source'):
                raise BusinessError('SOURCE_REQUIRED', '引用题目必须保留版本来源，或创建新的题位', question_id=question.id)
            continue
        source = question.source.model_dump()
        version = await db.question_versions.find_one({'_id': source['version_id'], 'question_id': source['question_id']})
        if not version or content_of(question) != version['content']:
            raise BusinessError('SOURCE_MISMATCH', '题目内容与引用版本不一致，请创建新版本或另存新题', question_id=question.id)
        retained = previous.get('source') == source and content_of(previous) == version['content']
        if not retained:
            await library.version(source['question_id'], source['version_id'], True)
