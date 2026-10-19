import math

import pytest

from backend.app.errors import BusinessError
from backend.app.examples import soccer_definition
from backend.app.logic import check_definition, evaluate, validate_answer
from backend.app.schemas import Answer, Definition, Question


def answers(**values):
    return [Answer(question_id=key, value=value) for key, value in values.items()]


def test_demo_has_valid_definition_and_expected_branches():
    definition = soccer_definition()
    assert check_definition(definition).valid
    _, path, end = evaluate(definition, answers(participate='no', reason='暂时没有时间'))
    assert path == ['participate', 'reason', 'other'] and end == 'END'
    _, path, _ = evaluate(definition, answers(participate='yes', sessions=2, suggestions='希望增加训练时间'))
    assert path == ['participate', 'sessions', 'suggestions', 'other']
    _, path, _ = evaluate(definition, answers(participate='yes', sessions=3, activities=['training']))
    assert path == ['participate', 'sessions', 'activities', 'other']
    _, path, _ = evaluate(definition, answers(participate='yes', sessions=3, activities=['match'], suggestions='希望多举办比赛'))
    assert path == ['participate', 'sessions', 'activities', 'suggestions', 'other']


@pytest.mark.parametrize('value', [True, False, '3', math.inf, -math.inf, math.nan, -1, 15, 1.5, [], {}, 10**400])
def test_number_rejects_invalid_values(value):
    with pytest.raises(BusinessError):
        validate_answer(soccer_definition().questions[1], value)


def test_zero_and_optional_empty_are_distinct():
    assert validate_answer(soccer_definition().questions[1], 0) == 0
    assert validate_answer(soccer_definition().questions[-1], '') is None


@pytest.mark.parametrize('value', [['match', 'match'], ['unknown'], ['match', 'training', 'social'], [], 'match'])
def test_multiple_choice_limits(value):
    with pytest.raises(BusinessError):
        validate_answer(soccer_definition().questions[2], value)


def test_exact_choice_limit_and_contains_all_priority():
    q = Question.model_validate({'id': 'q', 'type': 'multiple_choice', 'title': '多选',
        'options': [{'id': 'a', 'text': 'A'}, {'id': 'b', 'text': 'B'}],
        'validation': {'min_choices': 2, 'max_choices': 2},
        'routing': {'rules': [{'operator': 'contains_all', 'value': ['a', 'b'], 'target': 'END'},
                              {'operator': 'contains_any', 'value': ['a'], 'target': 'next'}]}})
    d = Definition(questions=[q, Question(id='next', type='text', title='后续', required=False)])
    normalized, path, _ = evaluate(d, answers(q=['b', 'a']))
    assert path == ['q'] and normalized[0]['value'] == ['a', 'b']
    with pytest.raises(BusinessError):
        validate_answer(q, ['a'])


def test_rejects_duplicate_unknown_and_off_path_answers():
    d = soccer_definition()
    for value in [answers(participate='no', reason='没有时间', sessions=2),
                  answers(participate='no', reason='没有时间', unknown=3),
                  answers(participate='no', reason='没有时间') + answers(reason='其他原因')]:
        with pytest.raises(BusinessError):
            evaluate(d, value)


def test_prefix_replay_prevents_forged_progress():
    with pytest.raises(BusinessError):
        evaluate(soccer_definition(), answers(reason='没有时间'), 'reason')
    with pytest.raises(BusinessError):
        evaluate(soccer_definition(), answers(participate='no', reason='没有时间'), 'activities')


@pytest.mark.parametrize('mutation', ['backward', 'unknown', 'bad_operator', 'bad_option', 'range', 'duplicate'])
def test_publish_checks(mutation):
    d = soccer_definition()
    if mutation == 'backward': d.questions[1].routing.default_target = 'participate'
    if mutation == 'unknown': d.questions[0].routing.default_target = 'missing'
    if mutation == 'bad_operator': d.questions[0].routing.rules[0].operator = 'gt'
    if mutation == 'bad_option': d.questions[0].routing.rules[0].value = 'missing'
    if mutation == 'range': d.questions[1].validation.min_value = 20
    if mutation == 'duplicate': d.questions[1].id = d.questions[0].id
    assert not check_definition(d).valid


def test_text_trim_unicode_length_and_empty_required():
    q = Question.model_validate({'id': 'q', 'type': 'text', 'title': '文字', 'validation': {'min_length': 2, 'max_length': 2}})
    assert validate_answer(q, ' 你🙂 ') == '你🙂'
    for value in [' ', 'a', 'abc', 0, True]:
        with pytest.raises(BusinessError): validate_answer(q, value)


def test_required_text_must_allow_a_nonempty_answer():
    question = Question(id='text', type='text', title='必答文本', validation={'max_length': 0})
    result = check_definition(Definition(questions=[question]))
    assert not result.valid
    assert any(issue.code == 'INVALID_RANGE' and issue.question_id == 'text' for issue in result.errors)

    question.required = False
    assert check_definition(Definition(questions=[question])).valid
    assert validate_answer(question, '') is None


@pytest.mark.parametrize('minimum,maximum', [
    (0.1, 0.9), (-0.9, -0.1), (2**53, None), (None, -(2**53)),
])
def test_integer_range_must_contain_a_supported_integer(minimum, maximum):
    question = Question(id='number', type='number', title='整数', validation={
        'min_value': minimum, 'max_value': maximum, 'integer_only': True,
    })
    result = check_definition(Definition(questions=[question]))
    assert not result.valid
    assert any(issue.code == 'INVALID_RANGE' and issue.question_id == 'number' for issue in result.errors)


@pytest.mark.parametrize('minimum,maximum,value', [
    (0.1, 1, 1), (-1, -0.1, -1), (0, 0, 0), (None, None, 0),
    (None, -1, -1), (1, None, 1), (2**53 - 1, 2**53 - 1, 2**53 - 1),
])
def test_integer_range_includes_endpoints_and_handles_missing_bounds(minimum, maximum, value):
    question = Question(id='number', type='number', title='整数', validation={
        'min_value': minimum, 'max_value': maximum, 'integer_only': True,
    })
    assert check_definition(Definition(questions=[question])).valid
    assert validate_answer(question, value) == value


def test_fractional_range_is_valid_when_decimals_are_allowed():
    question = Question(id='number', type='number', title='小数', validation={
        'min_value': 0.1, 'max_value': 0.9,
    })
    assert check_definition(Definition(questions=[question])).valid
    assert validate_answer(question, 0.5) == 0.5
