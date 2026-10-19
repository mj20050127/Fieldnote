from .schemas import Definition


def soccer_definition():
    def choice(qid, title, options, rules=None, default='NEXT'):
        return {'id': qid, 'type': 'single_choice', 'title': title, 'required': True,
                'options': [{'id': oid, 'text': text} for oid, text in options],
                'routing': {'rules': rules or [], 'default_target': default}}

    return Definition.model_validate({
        'title': '校园足球活动参与调查',
        'description': '让每一种热爱都被看见。用两分钟，帮助我们设计更适合你的校园足球活动。',
        'settings': {'allow_anonymous': True, 'allow_multiple': False},
        'questions': [
            choice('participate', '你目前参加校园足球活动吗？', [('yes', '参加，经常在球场见！'), ('no', '暂时没有参加')],
                   [{'operator': 'eq', 'value': 'no', 'target': 'reason'}]),
            {'id': 'sessions', 'type': 'number', 'title': '你每周大约踢几次球？', 'required': True,
             'description': '请填写 0～14 之间的整数。',
             'validation': {'min_value': 0, 'max_value': 14, 'integer_only': True},
             'routing': {'rules': [{'operator': 'gte', 'value': 3, 'target': 'activities'}], 'default_target': 'suggestions'}},
            {'id': 'activities', 'type': 'multiple_choice', 'title': '你最期待哪些足球活动？', 'required': True,
             'options': [{'id': 'training', 'text': '日常训练'}, {'id': 'match', 'text': '校园比赛'},
                         {'id': 'social', 'text': '轻松约球'}],
             'validation': {'min_choices': 1, 'max_choices': 2},
             'routing': {'rules': [{'operator': 'contains_any', 'value': ['match'], 'target': 'suggestions'}], 'default_target': 'other'}},
            {'id': 'suggestions', 'type': 'text', 'title': '对训练或比赛，你有什么建议？', 'required': True,
             'validation': {'min_length': 5, 'max_length': 100}, 'routing': {'default_target': 'other'}},
            {'id': 'reason', 'type': 'text', 'title': '是什么让你还没有参加？', 'required': True,
             'validation': {'min_length': 2, 'max_length': 100}},
            {'id': 'other', 'type': 'text', 'title': '还有什么想告诉我们的吗？', 'required': False,
             'description': '任何想法都欢迎，也可以直接跳过。', 'validation': {'max_length': 200}},
        ],
    })
