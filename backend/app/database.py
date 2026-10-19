from pymongo import ASCENDING, DESCENDING


async def initialize_database(db):
    """Idempotent collection validators and indexes; never clears existing data."""
    specifications = {
        'users': ({'_id': 'string', 'username': 'string', 'username_key': 'string',
                   'password_hash': 'string', 'created_at': 'date'}, []),
        'surveys': ({'_id': 'string', 'owner_id': 'string', 'public_code': 'string',
                     'title': 'string', 'description': 'string', 'settings': 'object',
                     'questions': 'array', 'revision': 'int', 'schema_version': 'int',
                     'definition_version': 'int', 'created_at': 'date', 'updated_at': 'date'},
                    ['status']),
        'responses': ({'_id': 'string', 'survey_id': 'string', 'respondent_id': 'string',
                       'definition_version': 'int', 'schema_version': 'int',
                       'is_anonymous': 'bool', 'single_submission': 'bool',
                       'answers': 'array', 'visited_question_ids': 'array',
                       'request_id': 'string', 'payload_hash': 'string', 'submitted_at': 'date'}, []),
        'sessions': ({'_id': 'string', 'user_id': 'string', 'csrf_token': 'string',
                      'expires_at': 'date', 'created_at': 'date'}, []),
    }
    existing = await db.list_collection_names()
    for name, (fields, additional) in specifications.items():
        properties = {field: {'bsonType': kind} for field, kind in fields.items()}
        if name == 'surveys':
            properties['status'] = {'enum': ['draft', 'published', 'closed']}
            properties['deadline'] = {'bsonType': ['date', 'null']}
            properties['settings'] = {
                'bsonType': 'object', 'required': ['allow_anonymous', 'allow_multiple'],
                'properties': {key: {'bsonType': 'bool'} for key in ['allow_anonymous', 'allow_multiple']}}
            properties['questions'] = {
                'bsonType': 'array', 'maxItems': 100, 'items': {
                    'bsonType': 'object',
                    'required': ['id', 'type', 'title', 'description', 'required', 'options', 'validation', 'routing'],
                    'properties': {
                        'id': {'bsonType': 'string', 'pattern': '^[a-zA-Z0-9_-]{1,80}$'},
                        'type': {'enum': ['single_choice', 'multiple_choice', 'text', 'number']},
                        'title': {'bsonType': 'string', 'maxLength': 500},
                        'description': {'bsonType': 'string', 'maxLength': 1000},
                        'required': {'bsonType': 'bool'},
                        'options': {'bsonType': 'array', 'maxItems': 50, 'items': {
                            'bsonType': 'object', 'required': ['id', 'text'], 'properties': {
                                'id': {'bsonType': 'string'}, 'text': {'bsonType': 'string', 'maxLength': 200}}}},
                        'validation': {'bsonType': 'object'},
                        'routing': {'bsonType': 'object', 'required': ['rules', 'default_target'], 'properties': {
                            'default_target': {'bsonType': 'string'},
                            'rules': {'bsonType': 'array', 'maxItems': 20, 'items': {
                                'bsonType': 'object', 'required': ['operator', 'value', 'target'], 'properties': {
                                    'operator': {'enum': ['eq', 'contains_any', 'contains_all', 'gt', 'gte', 'lt', 'lte']},
                                    'target': {'bsonType': 'string'}}}}}},
                    }}}
        if name == 'responses':
            properties['answers'] = {'bsonType': 'array', 'maxItems': 100,
                                     'items': {'bsonType': 'object', 'required': ['question_id', 'value'],
                                               'properties': {'question_id': {'bsonType': 'string'},
                                                   'value': {'bsonType': ['string', 'array', 'double', 'int', 'long']}}}}
            properties['visited_question_ids'] = {'bsonType': 'array', 'maxItems': 100, 'uniqueItems': True,
                                                  'items': {'bsonType': 'string'}}
        validator = {'$jsonSchema': {'bsonType': 'object', 'required': [*fields, *additional],
                                    'properties': properties}}
        if name in existing:
            await db.command({'collMod': name, 'validator': validator, 'validationLevel': 'strict'})
        else:
            await db.create_collection(name, validator=validator)
    await db.users.create_index('username_key', unique=True, name='unique_username')
    await db.surveys.create_index('public_code', unique=True, name='unique_public_code')
    await db.surveys.create_index([('owner_id', ASCENDING), ('created_at', DESCENDING)], name='owner_surveys')
    await db.responses.create_index([('survey_id', ASCENDING), ('submitted_at', DESCENDING)], name='survey_responses')
    await db.responses.create_index([('survey_id', ASCENDING), ('respondent_id', ASCENDING),
                                     ('request_id', ASCENDING)], unique=True, name='unique_request')
    await db.responses.create_index([('survey_id', ASCENDING), ('respondent_id', ASCENDING)],
                                    unique=True, partialFilterExpression={'single_submission': True},
                                    name='single_submission_per_user')
    await db.sessions.create_index('expires_at', expireAfterSeconds=0, name='expired_sessions')

