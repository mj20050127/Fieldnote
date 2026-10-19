"""Opt-in, development-only demo fixtures. Never overwrites existing accounts."""
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pymongo import AsyncMongoClient
from backend.app.auth import password_hasher
from backend.app.config import Settings
from backend.app.database import initialize_database
from backend.app.examples import soccer_definition
from backend.app.repositories import utcnow
from backend.app.schemas import Definition, RevisionInput, Submission
from backend.app.services import SurveyService, submit


async def main():
    settings = Settings()
    if settings.production:
        raise SystemExit('Refusing to create demo credentials in production.')
    client = AsyncMongoClient(settings.mongo_uri, tz_aware=True)
    try:
        db = client[settings.mongo_database]
        await initialize_database(db)
        if await db.users.find_one({'username_key': 'demo'}):
            print('Demo account already exists; existing data left intact.')
            return
        user = {'_id': uuid4().hex, 'username': 'demo', 'username_key': 'demo',
                'password_hash': password_hasher.hash('Fieldnote2026!'), 'created_at': utcnow()}
        await db.users.insert_one(user)
        service = SurveyService(db)
        soccer = await service.create(soccer_definition(), user)
        await service.publish(soccer.id, RevisionInput(expected_revision=soccer.revision), user)
        stats_definition = Definition.model_validate({
            'title': '校园学习空间体验调查',
            'description': '演示问卷，包含 3 份可手算核对的示例答卷。让更好的学习空间，从倾听开始。',
            'settings': {'allow_anonymous': True, 'allow_multiple': True},
            'questions': [
                {'id': 'place', 'type': 'single_choice', 'title': '你更喜欢在哪里学习？',
                 'options': [{'id': 'A', 'text': '图书馆'}, {'id': 'B', 'text': '自习教室'}, {'id': 'C', 'text': '宿舍'}]},
                {'id': 'needs', 'type': 'multiple_choice', 'title': '你最看重哪些空间条件？',
                 'options': [{'id': 'X', 'text': '安静的环境'}, {'id': 'Y', 'text': '充足的座位'}, {'id': 'Z', 'text': '便利的插座'}]},
                {'id': 'hours', 'type': 'number', 'title': '你每周在这里学习多少小时？', 'required': False,
                 'validation': {'min_value': 0, 'max_value': 168}},
                {'id': 'advice', 'type': 'text', 'title': '你期待怎样的改变？', 'required': False},
            ],
        })
        result = await service.create(stats_definition, user)
        await service.publish(result.id, RevisionInput(expected_revision=result.revision), user)
        survey = await db.surveys.find_one({'_id': result.id})
        for place, needs, hours, text in [('A', ['X', 'Y'], 10, '希望延长周末开放时间。'),
                                          ('B', ['Y'], 20, '希望增加一些靠窗的座位。'),
                                          ('A', ['X', 'Z'], None, '想要更多方便充电的学习位。')]:
            answers = [{'question_id': 'place', 'value': place}, {'question_id': 'needs', 'value': needs},
                       {'question_id': 'advice', 'value': text}]
            if hours is not None:
                answers.append({'question_id': 'hours', 'value': hours})
            await submit(db, survey, Submission(request_id=uuid4().hex, definition_version=1,
                                                is_anonymous=True, answers=answers), user)
        await service.create(Definition.model_validate({
            'title': '下一次社团活动，一起决定', 'description': '收集大家的新点子，为下一次相聚留出更多可能。',
            'questions': [{'id': 'ideas', 'type': 'text', 'title': '你最期待什么样的社团活动？',
                           'validation': {'min_length': 2, 'max_length': 200}}],
        }), user)
        print('Demo fixtures created. Username: demo / Password: Fieldnote2026!')
        print('3 surveys; 3 explicitly labeled example responses. No real participant data.')
    finally:
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
