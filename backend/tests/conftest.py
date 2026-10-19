import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def environment():
    name = 'fieldnote_test_' + uuid4().hex
    settings = Settings(mongo_database=name, app_env='test')
    connection = MongoClient(settings.mongo_uri, tz_aware=True, serverSelectionTimeoutMS=3000)
    try:
        connection.admin.command('ping')
    except Exception as error:
        pytest.fail(f'Integration tests require a real MongoDB: {error}')
    with TestClient(create_app(settings)) as client:
        yield client, connection[name]
    assert name.startswith('fieldnote_test_')
    connection.drop_database(name)
    connection.close()


def register(client, username='owner'):
    response = client.post('/api/auth/register', json={'username': username, 'password': 'Test-password-2026!'})
    assert response.status_code == 201, response.text
    user = response.json()
    client.headers['X-CSRF-Token'] = user['csrf_token']
    return user


def create_published(client, questions=None, allow_multiple=False):
    if questions is None:
        questions = [{'id': 'rating', 'type': 'number', 'title': '评分', 'required': True,
                      'validation': {'min_value': 0, 'max_value': 10, 'integer_only': True}}]
    response = client.post('/api/surveys', json={'title': '测试问卷', 'questions': questions,
                                               'settings': {'allow_anonymous': True, 'allow_multiple': allow_multiple}})
    assert response.status_code == 201, response.text
    survey = response.json()
    published = client.post(f'/api/surveys/{survey["id"]}/publish', json={'expected_revision': survey['revision']})
    assert published.status_code == 200, published.text
    return published.json()


def submission(request_id=None, value=5):
    return {'request_id': request_id or uuid4().hex, 'definition_version': 1, 'is_anonymous': True,
            'answers': [{'question_id': 'rating', 'value': value}]}
