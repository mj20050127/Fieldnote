from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from pymongo.errors import WriteError

from conftest import create_published, register
from pymongo.asynchronous.collection import AsyncCollection


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def setup(client, content=None):
    bank = ok(client.post('/api/question-banks', json={'name': '常用题'}), 201)
    payload = {'request_id': uuid4().hex, 'bank_id': bank['id'], 'content': content or
               {'type': 'number', 'title': '年龄', 'required': False}}
    question = ok(client.post('/api/questions', json=payload), 201)
    return bank, question, payload


def slot(question, local='rating', version=None):
    v = version or question['latest_version']
    return dict(v['content'], id=local, source={'question_id': question['id'], 'version_id': v['id']})


def new_version(client, question, **changes):
    v = question['latest_version']
    return ok(client.post(f'/api/questions/{question["id"]}/versions', json={
        'request_id': uuid4().hex, 'parent_version_id': v['id'], 'content': v['content'] | changes}), 201)


def submit(client, survey, values):
    return ok(client.post(f'/api/forms/{survey["public_code"]}/responses', json={
        'request_id': uuid4().hex, 'definition_version': 1, 'is_anonymous': True,
        'answers': [{'question_id': qid, 'value': value} for qid, value in values.items()]}), 201)


def test_bank_metadata_archive_and_owner_isolation(environment):
    c, db = environment
    register(c)
    bank, question, _ = setup(c)
    updated = ok(c.patch('/api/question-banks/' + bank['id'], json={'expected_revision': 1, 'name': '访谈', 'archived': True}))
    assert updated['revision'] == 2
    assert c.get('/api/questions/' + question['id']).json()['available_for_reuse'] is False
    assert c.post('/api/surveys', json={'questions': [slot(question)]}).status_code == 409
    assert c.patch('/api/question-banks/' + bank['id'], json={'expected_revision': 1, 'name': '冲突'}).status_code == 409
    register(c, 'stranger')
    assert c.get('/api/question-banks').json()['items'] == []
    assert c.patch('/api/questions/' + question['id'], json={'expected_revision': 1, 'archived': True}).status_code == 404


def test_immutable_versions_branches_restore_and_idempotence(environment):
    c, db = environment
    register(c)
    _, question, payload = setup(c)
    root = '/api/questions/' + question['id']
    assert ok(c.post('/api/questions', json=payload), 201)['id'] == question['id']
    assert c.post('/api/questions', json=payload | {'content': {'type': 'text', 'title': '不同'}}).status_code == 409
    original = question['latest_version']
    data = {'request_id': uuid4().hex, 'parent_version_id': original['id'],
            'content': original['content'] | {'title': '年龄（周岁）'}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: c.post(root + '/versions', json=data), range(2)))
    assert all(r.status_code == 201 for r in results)
    assert results[0].json()['id'] == results[1].json()['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        branches = list(pool.map(lambda _: new_version(c, question, title='并行分支'), range(2)))
    assert len({b['version_no'] for b in branches}) == 2
    assert all(b['parent_version_id'] == original['id'] for b in branches)
    latest = ok(c.get(root))['latest_version']
    restored = ok(c.post(root + '/restore', json={'request_id': uuid4().hex,
        'target_version_id': original['id'], 'parent_version_id': latest['id']}), 201)
    assert restored['content'] == original['content'] and restored['restored_from_version_id'] == original['id']
    assert restored['version_no'] > latest['version_no']
    assert ok(c.get(root + '/versions?page_size=2'))['total'] == 5
    assert ok(c.get(root + '/versions/' + original['id'])) == original
    assert c.put(root + '/versions/' + original['id'], json=data).status_code == 405
    with pytest.raises(WriteError):
        db.question_versions.insert_one({'_id': 'broken'})


def test_shared_use_fork_revocation_historical_visibility(environment):
    c, db = environment
    owner = register(c, 'alice')
    _, question, _ = setup(c)
    root = '/api/questions/' + question['id']
    bob = register(c, 'bob')
    bank = ok(c.post('/api/question-banks', json={'name': '收到的题'}), 201)
    assert c.get(root).status_code == 404
    ok(c.post('/api/auth/login', json={'username': 'alice', 'password': 'Test-password-2026!'}))
    c.headers['X-CSRF-Token'] = c.get('/api/auth/me').json()['csrf_token']
    ok(c.post(root + '/shares', json={'expected_revision': 1, 'username': 'BOB'}))
    ok(c.post('/api/auth/login', json={'username': 'bob', 'password': 'Test-password-2026!'}))
    c.headers['X-CSRF-Token'] = c.get('/api/auth/me').json()['csrf_token']
    assert ok(c.get('/api/questions?scope=shared'))['total'] == 1
    survey = create_published(c, [slot(question)])
    submit(c, survey, {'rating': 88})
    assert c.post(root + '/versions', json={'request_id': uuid4().hex, 'parent_version_id': question['latest_version']['id'],
                'content': question['latest_version']['content']}).status_code == 404
    fork = ok(c.post(root + '/fork', json={'request_id': uuid4().hex, 'bank_id': bank['id'],
        'source_version_id': question['latest_version']['id'], 'content': question['latest_version']['content'] | {'title': '我的年龄'}}), 201)
    assert fork['owner_id'] == bob['id'] and fork['derived_from']['question_id'] == question['id']
    ok(c.post('/api/auth/login', json={'username': 'alice', 'password': 'Test-password-2026!'}))
    c.headers['X-CSRF-Token'] = c.get('/api/auth/me').json()['csrf_token']
    assert ok(c.get(root + '/usages'))['total'] == 0
    assert ok(c.get(root + '/statistics'))['groups'][0]['response_count'] == 0
    ok(c.request('DELETE', root + '/shares/' + bob['id'], json={'expected_revision': 2}))
    v2 = new_version(c, question, title='不再共享的新版')
    ok(c.post('/api/auth/login', json={'username': 'bob', 'password': 'Test-password-2026!'}))
    c.headers['X-CSRF-Token'] = c.get('/api/auth/me').json()['csrf_token']
    historical = ok(c.get(root))
    assert historical['access'] == 'historical' and historical['latest_version']['version_no'] == 1
    assert c.get(root + '/versions/' + v2['id']).status_code == 404
    assert ok(c.get(root + '/versions'))['total'] == 1
    assert ok(c.get(root + '/statistics'))['groups'][0]['average'] == 88
    assert c.post('/api/surveys', json={'questions': [slot(question)]}).status_code == 404
    assert c.get('/api/forms/' + survey['public_code']).status_code == 200
    register(c, 'charlie')
    assert c.get(root + '/statistics').status_code == 404


def test_snapshot_integrity_version_swap_and_invalid_routes(environment):
    c, db = environment
    register(c)
    _, question, _ = setup(c, {'type': 'single_choice', 'title': '选择', 'options': [{'id': 'a', 'text': '甲'}, {'id': 'b', 'text': '乙'}]})
    published = create_published(c, [slot(question)])
    before = db.surveys.find_one({'_id': published['id']})
    v2 = new_version(c, question, options=[{'id': 'a', 'text': '甲'}, {'id': 'c', 'text': '丙'}])
    assert db.surveys.find_one({'_id': published['id']}) == before
    forged = slot(question) | {'title': '伪造'}
    assert c.post('/api/surveys', json={'questions': [forged]}).status_code == 422
    draft = ok(c.post('/api/surveys', json={'questions': [slot(question)]}), 201)
    changed = slot(question, version=v2) | {'routing': {'rules': [{'operator': 'eq', 'value': 'b', 'target': 'END'}], 'default_target': 'NEXT'}}
    saved = ok(c.put(f'/api/surveys/{draft["id"]}/definition', json={'title': '草稿', 'questions': [changed], 'expected_revision': 1}))
    assert saved['questions'][0]['id'] == 'rating'
    check = ok(c.post(f'/api/surveys/{draft["id"]}/validate', json={}))
    assert any(i['code'] == 'INVALID_RULE' and i['question_id'] == 'rating' for i in check['errors'])
    assert c.post(f'/api/surveys/{draft["id"]}/publish', json={'expected_revision': 2}).status_code == 422


def test_cross_statistics_duplicate_slots_versions_and_owner_scope(environment):
    c, db = environment
    register(c)
    _, question, _ = setup(c)
    a = create_published(c, [slot(question, 'first'), slot(question, 'second')], True)
    b = create_published(c, [slot(question)], True)
    submit(c, a, {'first': 10, 'second': 20})
    submit(c, b, {'rating': 30})
    submit(c, b, {})
    root = '/api/questions/' + question['id']
    v2 = new_version(c, question, title='另一版本')
    other = create_published(c, [slot(question, version=v2)], True)
    submit(c, other, {'rating': 999})
    stats = ok(c.get(root + '/statistics'))['groups']
    assert len(stats) == 2
    first = stats[0]
    assert (first['average'], first['minimum'], first['maximum']) == (20, 10, 30)
    assert (first['response_count'], first['occurrence_count'], first['answered_count'], first['unanswered_count']) == (3, 4, 3, 1)
    assert first['frequency_total'] == 3
    assert [f['value'] for f in first['frequencies']] == [10, 20, 30]
    filtered = ok(c.get(root + '/statistics', params={'survey_ids': a['id'], 'version_id': question['latest_version']['id']}))['groups'][0]
    assert filtered['average'] == 15 and filtered['response_count'] == 1
    assert ok(c.get(root + '/usages'))['total'] == 3


@pytest.mark.parametrize('kind,values,expected', [
    ('single_choice', ['a', 'b', 'a'], [2, 1]),
    ('multiple_choice', [['a', 'b'], ['a']], [2, 1]),
    ('text', ['甲', '乙'], [])])
def test_choice_text_statistics_and_pagination(environment, kind, values, expected):
    c, db = environment
    register(c)
    content = {'type': kind, 'title': '统计测试'}
    if 'choice' in kind:
        content['options'] = [{'id': 'a', 'text': '甲'}, {'id': 'b', 'text': '乙'}]
    _, question, _ = setup(c, content)
    survey = create_published(c, [slot(question)], True)
    for value in values:
        submit(c, survey, {'rating': value})
    group = ok(c.get(f'/api/questions/{question["id"]}/statistics?page_size=1&page=2'))['groups'][0]
    assert [o['count'] for o in group['options']] == expected
    assert group['answered_count'] == len(values) and len(group['values']) == 1


@pytest.mark.parametrize('phase', ['initial', 'version'])
def test_interrupted_insert_can_retry_without_duplicate_versions(environment, monkeypatch, phase):
    c, db = environment
    register(c)
    bank, question, payload = setup(c)
    original = AsyncCollection.insert_one
    failed = False
    async def interrupt(collection, *args, **kwargs):
        nonlocal failed
        if collection.name == 'question_versions' and not failed:
            failed = True
            raise RuntimeError('simulated process interruption')
        return await original(collection, *args, **kwargs)
    monkeypatch.setattr(AsyncCollection, 'insert_one', interrupt)
    if phase == 'initial':
        url = '/api/questions'
        payload['request_id'] = uuid4().hex
    else:
        url = '/api/questions/' + question['id'] + '/versions'
        payload = {'request_id': uuid4().hex, 'parent_version_id': question['latest_version']['id'], 'content': question['latest_version']['content']}
    with pytest.raises(RuntimeError, match='simulated'):
        c.post(url, json=payload)
    assert ok(c.get('/api/questions'))['total'] == 1  # unfinished family stays hidden
    result = ok(c.post(url, json=payload), 201)
    replay = ok(c.post(url, json=payload), 201)
    assert result['id'] == replay['id']
    if phase == 'version':
        assert result['version_no'] == 3  # failed allocated number 2 is an allowed gap
    assert db.question_versions.count_documents({'request_id': payload['request_id']}) == 1


def test_route_population_and_archived_snapshot_retention(environment):
    c, db = environment
    register(c)
    bank, question, _ = setup(c)
    gate = {'id': 'gate', 'type': 'single_choice', 'title': '继续？', 'options': [
        {'id': 'yes', 'text': '继续'}, {'id': 'no', 'text': '结束'}],
        'routing': {'rules': [{'operator': 'eq', 'value': 'no', 'target': 'END'}]}}
    survey = create_published(c, [gate, slot(question, 'first'), slot(question, 'second')], True)
    submit(c, survey, {'gate': 'no'})
    submit(c, survey, {'gate': 'yes', 'first': 10})
    root = '/api/questions/' + question['id']
    group = ok(c.get(root + '/statistics'))['groups'][0]
    assert (group['occurrence_count'], group['reached_count'], group['answered_count'],
            group['skipped_count'], group['unanswered_count']) == (4, 2, 1, 2, 1)
    draft = ok(c.post('/api/surveys', json={'questions': [slot(question)]}), 201)
    ok(c.patch(root, json={'expected_revision': 1, 'archived': True}))
    assert c.post('/api/surveys', json={'questions': [slot(question)]}).status_code == 409
    ok(c.put(f'/api/surveys/{draft["id"]}/definition', json={'title': '仍可保存既有快照', 'questions': draft['questions'], 'expected_revision': 1}))
    assert ok(c.get(root + '/statistics'))['groups'][0]['average'] == 10
    detached = draft['questions'][0] | {'source': None}
    assert c.put(f'/api/surveys/{draft["id"]}/definition', json={'questions': [detached], 'expected_revision': 2}).status_code == 422
