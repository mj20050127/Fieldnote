import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from pymongo.errors import WriteError

from backend.app.auth import token_hash
from backend.app.repositories import utcnow
from conftest import create_published, register, submission


def test_auth_normalization_logout_and_csrf(environment):
    client, db = environment
    register(client, 'Owner')
    assert client.post('/api/auth/register', json={'username': 'owner', 'password': '12345678'}).status_code == 409
    assert client.post('/api/auth/login', json={'username': 'Owner', 'password': 'wrong-pass'}).status_code == 401
    assert client.post('/api/surveys', json={'title': 'CSRF'}, headers={'X-CSRF-Token': ''}).status_code == 403
    assert client.post('/api/surveys', json={'title': 'Origin'}, headers={'Origin': 'https://evil.example'}).status_code == 403
    cookie = client.cookies.get('fieldnote_session')
    assert client.post('/api/auth/logout', json={}).status_code == 204
    assert client.get('/api/auth/me').status_code == 401
    assert db.sessions.find_one({'_id': token_hash(cookie)}) is None


def test_expired_session_rejected_before_ttl_cleanup(environment):
    client, db = environment
    register(client)
    db.sessions.update_many({}, {'$set': {'expires_at': utcnow() - timedelta(seconds=1)}})
    assert client.get('/api/auth/me').status_code == 401


def test_draft_save_publish_revision_and_freeze(environment):
    client, db = environment
    register(client)
    draft = client.post('/api/surveys', json={'title': '草稿'}).json()
    url = f'/api/surveys/{draft["id"]}'
    assert client.post(url + '/publish', json={'expected_revision': 1}).status_code == 422
    template = client.get('/api/templates/soccer').json()
    saved = client.put(url + '/definition', json={**template, 'expected_revision': 1})
    assert saved.status_code == 200
    assert client.put(url + '/definition', json={**template, 'expected_revision': 1}).status_code == 409
    assert client.post(url + '/validate', json={}).json()['valid'] is True
    result = client.post(url + '/publish', json={'expected_revision': 2})
    assert result.status_code == 200
    assert client.put(url + '/definition', json={**template, 'expected_revision': 3}).status_code == 409
    preview = client.post(url + '/preview', json={'current_question_id': 'participate', 'answers': [{'question_id': 'participate', 'value': 'no'}]})
    assert preview.json()['next_question_id'] == 'reason'
    assert db.responses.count_documents({}) == 0


def test_permissions_on_all_management_routes(environment):
    client, db = environment
    owner = register(client)
    survey = create_published(client)
    receipt = client.post(f'/api/forms/{survey["public_code"]}/responses', json=submission()).json()
    register(client, 'another')
    root = f'/api/surveys/{survey["id"]}'
    for path in ['', '/statistics', '/responses', f'/responses/{receipt["id"]}', '/questions/rating/statistics']:
        assert client.get(root + path).status_code == 404
    for path, body in [('/close', {'expected_revision': 2}), ('/validate', {}), ('/publish', {'expected_revision': 2})]:
        assert client.post(root + path, json=body).status_code == 404
    assert client.get('/api/surveys').json()['total'] == 0
    assert client.get('/api/overview').json()['total_responses'] == 0


def test_submission_retry_conflict_and_retry_after_close(environment):
    client, db = environment
    register(client)
    survey = create_published(client)
    url = f'/api/forms/{survey["public_code"]}/responses'
    payload = submission()
    first = client.post(url, json=payload)
    assert first.status_code == 201
    retry = client.post(url, json=payload)
    assert retry.status_code == 200 and retry.json()['id'] == first.json()['id']
    assert client.post(url, json={**payload, 'answers': [{'question_id': 'rating', 'value': 6}]}).status_code == 409
    assert client.post(url, json=submission()).status_code == 409
    assert client.post(f'/api/surveys/{survey["id"]}/close', json={'expected_revision': survey['revision']}).status_code == 200
    assert client.post(url, json=payload).status_code == 200
    assert client.post(url, json=submission()).status_code == 409
    assert db.responses.count_documents({}) == 1


def test_deadline_and_draft_visibility(environment):
    client, db = environment
    register(client)
    draft = client.post('/api/surveys', json={'title': '未发布'}).json()
    assert client.get(f'/api/forms/{draft["public_code"]}').status_code == 404
    survey = create_published(client)
    db.surveys.update_one({'_id': survey['id']}, {'$set': {'deadline': utcnow() - timedelta(seconds=1)}})
    assert client.get(f'/api/forms/{survey["public_code"]}').json()['effective_status'] == 'expired'
    assert client.post(f'/api/forms/{survey["public_code"]}/responses', json=submission()).status_code == 409
    assert client.get('/api/surveys?status=expired').json()['total'] == 1


def test_deadline_updates_keep_definition_and_advance_revision(environment):
    client, db = environment
    register(client)
    definition = client.get('/api/templates/soccer').json()
    draft = client.post('/api/surveys', json=definition).json()
    root = f'/api/surveys/{draft["id"]}'
    future = (utcnow() + timedelta(days=1)).isoformat()

    result = client.patch(root, json={'expected_revision': 1, 'deadline': future})
    assert result.status_code == 200, result.text
    updated = result.json()
    assert updated['revision'] == 2 and updated['deadline'] is not None
    assert updated['questions'] == draft['questions'] and updated['title'] == draft['title']

    edited = {**definition, 'title': '修改后的标题', 'expected_revision': updated['revision']}
    saved = client.put(root + '/definition', json=edited)
    assert saved.status_code == 200, saved.text
    assert client.patch(root, json={'expected_revision': 2, 'deadline': None}).status_code == 409
    cleared = client.patch(root, json={'expected_revision': saved.json()['revision'], 'deadline': None})
    assert cleared.status_code == 200 and cleared.json()['deadline'] is None
    assert cleared.json()['title'] == edited['title']

    published = client.post(root + '/publish', json={'expected_revision': cleared.json()['revision']})
    assert published.status_code == 200
    revision = published.json()['revision']
    changed = client.patch(root, json={'expected_revision': revision, 'deadline': future})
    assert changed.status_code == 200 and changed.json()['revision'] == revision + 1
    form = client.get(f'/api/forms/{draft["public_code"]}').json()
    assert form['deadline'] == changed.json()['deadline']
    for invalid in [(utcnow() - timedelta(seconds=1)).isoformat(), '2030-01-01T12:00:00']:
        rejected = client.patch(root, json={'expected_revision': revision + 1, 'deadline': invalid})
        assert rejected.status_code == 422
    assert client.get(root).json()['revision'] == revision + 1


@pytest.mark.parametrize('kind,invalid,fixed,value', [
    ('text', {'max_length': 0}, {'max_length': 1}, '字'),
    ('number', {'min_value': 0.1, 'max_value': 0.9, 'integer_only': True},
     {'min_value': 0.1, 'max_value': 1, 'integer_only': True}, 1),
])
def test_unsatisfiable_question_cannot_publish_until_fixed(environment, kind, invalid, fixed, value):
    client, db = environment
    register(client)
    definition = {'title': '发布检查回归', 'questions': [
        {'id': 'question', 'type': kind, 'title': '必答题', 'validation': invalid},
    ]}
    created = client.post('/api/surveys', json=definition)
    assert created.status_code == 201
    survey = created.json()
    root = f'/api/surveys/{survey["id"]}'
    check = client.post(root + '/validate', json={}).json()
    assert not check['valid']
    assert check['errors'][0]['question_id'] == 'question'
    rejected = client.post(root + '/publish', json={'expected_revision': 1})
    assert rejected.status_code == 422
    assert rejected.json()['error']['code'] == 'INVALID_RANGE'
    assert client.get(root).json()['status'] == 'draft'
    assert db.responses.count_documents({}) == 0

    definition['questions'][0]['validation'] = fixed
    saved = client.put(root + '/definition', json={**definition, 'expected_revision': 1})
    assert saved.status_code == 200
    assert client.post(root + '/validate', json={}).json()['valid']
    published = client.post(root + '/publish', json={'expected_revision': saved.json()['revision']})
    assert published.status_code == 200
    response = client.post(f'/api/forms/{survey["public_code"]}/responses', json={
        'request_id': uuid4().hex, 'definition_version': 1,
        'answers': [{'question_id': 'question', 'value': value}],
    })
    assert response.status_code == 201, response.text


def test_anonymous_projection_and_real_identity(environment):
    client, db = environment
    user = register(client)
    survey = create_published(client, allow_multiple=True)
    url = f'/api/forms/{survey["public_code"]}/responses'
    anon = client.post(url, json=submission()).json()
    client.post(url, json={**submission(), 'is_anonymous': False})
    listing = client.get(f'/api/surveys/{survey["id"]}/responses').json()
    assert {row['respondent'] for row in listing['items']} == {None, 'owner'}
    private = client.get(f'/api/surveys/{survey["id"]}/responses/{anon["id"]}').json()
    assert private['respondent'] is None
    assert all(key not in str(listing) for key in ['respondent_id', 'payload_hash', 'request_id'])


def test_real_mongodb_validators_and_indexes(environment):
    client, db = environment
    register(client)
    with pytest.raises(WriteError): db.responses.insert_one({'_id': 'invalid'})
    survey = create_published(client)
    with pytest.raises(WriteError):
        db.surveys.update_one({'_id': survey['id']}, {'$set': {'questions.0.required': 'yes'}})
    indexes = db.responses.index_information()
    assert indexes['unique_request']['unique']
    assert indexes['single_submission_per_user']['partialFilterExpression'] == {'single_submission': True}


def test_body_limit_covers_chunked_requests(environment):
    client, db = environment
    register(client)
    chunks = (b'x' * 65536 for _ in range(17))
    result = client.post('/api/surveys', content=chunks, headers={'Content-Type': 'application/json'})
    assert result.status_code == 413


def test_anonymity_disabled_and_version_guard(environment):
    client, db = environment
    register(client)
    survey = create_published(client)
    # Model a definition that disallowed anonymity before publishing; no API edits a published definition.
    db.surveys.update_one({'_id': survey['id']}, {'$set': {'settings.allow_anonymous': False}})
    url = f'/api/forms/{survey["public_code"]}/responses'
    assert client.post(url, json=submission()).status_code == 422
    assert client.post(url, json={**submission(), 'is_anonymous': False, 'definition_version': 2}).status_code == 409
    assert client.post(url, json={**submission(), 'is_anonymous': False}).status_code == 201


def test_skipped_required_questions_and_statistics(environment):
    client, db = environment
    register(client)
    definition = client.get('/api/templates/soccer').json()
    definition['settings']['allow_multiple'] = True
    draft = client.post('/api/surveys', json=definition).json()
    survey = client.post(f'/api/surveys/{draft["id"]}/publish', json={'expected_revision': 1}).json()
    paths = [
        [{'question_id': 'participate', 'value': 'no'}, {'question_id': 'reason', 'value': '没有时间'}],
        [{'question_id': 'participate', 'value': 'yes'}, {'question_id': 'sessions', 'value': 3},
         {'question_id': 'activities', 'value': ['training']}],
    ]
    for answers in paths:
        result = client.post(f'/api/forms/{survey["public_code"]}/responses', json={
            'request_id': uuid4().hex, 'definition_version': 1, 'answers': answers})
        assert result.status_code == 201, result.text
    stats = client.get(f'/api/surveys/{survey["id"]}/statistics').json()
    questions = {q['question_id']: q for q in stats['questions']}
    assert questions['sessions']['skipped_count'] == 1
    assert questions['suggestions']['skipped_count'] == 2
    assert questions['other']['reached_count'] == 2 and questions['other']['unanswered_count'] == 2


def test_hand_calculated_statistics(environment):
    client, db = environment
    register(client)
    questions = [
        {'id': 'single', 'type': 'single_choice', 'title': '单选', 'options': [{'id': i, 'text': i} for i in ['A', 'B', 'C']]},
        {'id': 'multi', 'type': 'multiple_choice', 'title': '多选', 'options': [{'id': i, 'text': i} for i in ['X', 'Y', 'Z']]},
        {'id': 'number', 'type': 'number', 'title': '数字', 'required': False},
        {'id': 'empty', 'type': 'number', 'title': '无回答', 'required': False},
    ]
    survey = create_published(client, questions, allow_multiple=True)
    for single, multi, value in [('A', ['X', 'Y'], 10), ('B', ['Y'], 20), ('A', ['X', 'Z'], None)]:
        data = {'request_id': uuid4().hex, 'definition_version': 1, 'answers': [
            {'question_id': 'single', 'value': single}, {'question_id': 'multi', 'value': multi}]}
        if value is not None: data['answers'].append({'question_id': 'number', 'value': value})
        assert client.post(f'/api/forms/{survey["public_code"]}/responses', json=data).status_code == 201
    stats = client.get(f'/api/surveys/{survey["id"]}/statistics').json()
    assert stats['total_responses'] == 3
    single, multi, number, empty = stats['questions']
    assert [o['count'] for o in single['options']] == [2, 1, 0]
    assert [o['count'] for o in multi['options']] == [2, 2, 1]
    assert number['average'] == 15 and number['answered_count'] == 2
    assert number['unanswered_count'] == 1 and empty['average'] is None
    values = client.get(f'/api/surveys/{survey["id"]}/questions/number/statistics?page_size=1').json()
    assert values['total'] == 2 and len(values['values']) == 1
    assert client.get('/api/overview').json()['total_responses'] == 3


@pytest.mark.parametrize('mode,expected', [('different_users', 50), ('single_user', 1), ('same_request', 1), ('multiple_allowed', 20)])
def test_concurrent_submissions(environment, mode, expected):
    client, db = environment
    owner = register(client)
    survey = create_published(client, allow_multiple=mode == 'multiple_allowed')
    payload = submission()
    requests = []
    count = 50 if mode == 'different_users' else 20
    for i in range(count):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        user_id = f'participant_{i}' if mode == 'different_users' else owner['id']
        if mode == 'different_users':
            db.users.insert_one({'_id': user_id, 'username': user_id, 'username_key': user_id,
                                 'password_hash': 'seeded-test-only', 'created_at': utcnow()})
        db.sessions.insert_one({'_id': token_hash(token), 'user_id': user_id, 'csrf_token': csrf,
                                'created_at': utcnow(), 'expires_at': utcnow() + timedelta(hours=1)})
        requests.append(({'Cookie': f'fieldnote_session={token}', 'X-CSRF-Token': csrf},
                         payload if mode == 'same_request' else submission()))
    def send(item):
        headers, body = item
        return client.post(f'/api/forms/{survey["public_code"]}/responses', json=body, headers=headers)
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(send, requests))
    assert db.responses.count_documents({'survey_id': survey['id']}) == expected
    assert all(result.status_code in (200, 201, 409) for result in results)
    if mode == 'same_request': assert len({result.json()['id'] for result in results}) == 1
    if mode == 'different_users': assert all(result.status_code == 201 for result in results)
