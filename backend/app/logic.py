"""Pure questionnaire validation and routing; shared by preview and submissions."""
import math
from collections import Counter

from .errors import BusinessError
from .schemas import Answer, Definition, DefinitionCheck, Issue, Question


MAX_SAFE_NUMBER = 2**53 - 1


def is_number(value) -> bool:
    return type(value) in (int, float) and abs(value) <= MAX_SAFE_NUMBER and math.isfinite(value)


def check_definition(definition: Definition) -> DefinitionCheck:
    errors, warnings = [], []

    def error(code, message, qid=None):
        errors.append(Issue(code=code, message=message, question_id=qid))

    questions = definition.questions
    if not definition.title.strip():
        error('EMPTY_TITLE', '请填写问卷标题')
    if not questions:
        error('NO_QUESTIONS', '至少添加一道题目')
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids) or {'NEXT', 'END'} & set(ids):
        error('DUPLICATE_ID', '题目 ID 必须唯一，且不能使用 NEXT 或 END')
    positions = {qid: i for i, qid in enumerate(ids)}
    edges = {qid: [] for qid in ids}
    for index, question in enumerate(questions):
        qid, kind, limits = question.id, question.type, question.validation
        if not question.title.strip():
            error('EMPTY_QUESTION', '请填写题目标题', qid)
        option_ids = [o.id for o in question.options]
        if kind in ('single_choice', 'multiple_choice'):
            if len(option_ids) < 2 or len(set(option_ids)) != len(option_ids):
                error('INVALID_OPTIONS', '选择题至少需要两个选项，且选项 ID 不能重复', qid)
            if any(not o.text.strip() for o in question.options):
                error('EMPTY_OPTION', '选项内容不能为空', qid)
        elif question.options:
            error('UNEXPECTED_OPTIONS', '填空题不能包含选项', qid)
        applicable = {'single_choice': set(), 'multiple_choice': {'min_choices', 'max_choices'},
                      'text': {'min_length', 'max_length'},
                      'number': {'min_value', 'max_value', 'integer_only'}}[kind]
        for name, value in limits.model_dump().items():
            if value is not None and value is not False and name not in applicable:
                error('INVALID_LIMIT', '校验限制与题型不匹配', qid)
        for lower, upper in [('min_choices', 'max_choices'), ('min_length', 'max_length'),
                             ('min_value', 'max_value')]:
            lo, hi = getattr(limits, lower), getattr(limits, upper)
            if lo is not None and hi is not None and lo > hi:
                error('INVALID_RANGE', '最小限制不能大于最大限制', qid)
        if kind == 'multiple_choice':
            if any(v is not None and v > len(option_ids)
                   for v in [limits.min_choices, limits.max_choices]):
                error('INVALID_CHOICES', '选择数量不能超过选项总数', qid)
            if question.required and limits.max_choices == 0:
                error('INVALID_CHOICES', '必答多选题必须允许至少选择一项', qid)
        if kind == 'text' and question.required and limits.max_length == 0:
            error('INVALID_RANGE', '必答文本题必须允许至少填写 1 字', qid)
        if kind == 'number' and limits.integer_only:
            minimum = max(-MAX_SAFE_NUMBER, limits.min_value if limits.min_value is not None else -MAX_SAFE_NUMBER)
            maximum = min(MAX_SAFE_NUMBER, limits.max_value if limits.max_value is not None else MAX_SAFE_NUMBER)
            if math.ceil(minimum) > math.floor(maximum):
                error('INVALID_RANGE', '整数题的范围必须包含至少一个有效整数', qid)
        for rule in question.routing.rules:
            valid = False
            if kind == 'single_choice':
                valid = rule.operator == 'eq' and isinstance(rule.value, str) and rule.value in option_ids
            elif kind == 'multiple_choice':
                valid = rule.operator in ('contains_any', 'contains_all') and isinstance(rule.value, list)
                valid = valid and bool(rule.value) and all(isinstance(v, str) and v in option_ids for v in rule.value)
                valid = valid and len(set(rule.value)) == len(rule.value)
            elif kind == 'number':
                valid = rule.operator in ('eq', 'gt', 'gte', 'lt', 'lte') and is_number(rule.value)
            if not valid:
                error('INVALID_RULE', '跳转条件与题型不匹配，或条件值无效', qid)
        for target in [question.routing.default_target, *[r.target for r in question.routing.rules]]:
            if target == 'NEXT':
                target = ids[index + 1] if index + 1 < len(ids) else 'END'
            if target == 'END':
                continue
            if target not in positions or positions[target] <= index:
                error('INVALID_TARGET', '只能跳转到后续存在的题目或结束问卷', qid)
            else:
                edges[qid].append(target)
    if questions and not errors:
        reachable, pending = set(), [ids[0]]
        while pending:
            current = pending.pop()
            if current not in reachable:
                reachable.add(current)
                pending.extend(edges[current])
        for qid in ids:
            if qid not in reachable:
                warnings.append(Issue(code='UNREACHABLE', message='该题在当前跳转结构中不可到达', question_id=qid))
    return DefinitionCheck(valid=not errors, errors=errors, warnings=warnings)


def validate_answer(question: Question, value):
    def fail(message):
        raise BusinessError('INVALID_ANSWER', message, question_id=question.id)

    if isinstance(value, str) and question.type == 'text':
        value = value.strip()
    empty = value is None or value == '' or value == []
    if empty:
        if question.required:
            fail('这道题为必答题，请先填写')
        return None
    kind, limits = question.type, question.validation
    options = {option.id for option in question.options}
    if kind == 'single_choice':
        if not isinstance(value, str) or value not in options:
            fail('请选择有效的选项')
    elif kind == 'multiple_choice':
        if not isinstance(value, list) or any(not isinstance(v, str) or v not in options for v in value):
            fail('请选择有效的选项')
        if len(set(value)) != len(value):
            fail('选项不能重复')
        if limits.min_choices is not None and len(value) < limits.min_choices:
            fail(f'至少选择 {limits.min_choices} 项')
        if limits.max_choices is not None and len(value) > limits.max_choices:
            fail(f'最多选择 {limits.max_choices} 项')
        value = sorted(value)
    elif kind == 'text':
        if not isinstance(value, str):
            fail('请输入文字')
        if len(value) > 10000:
            fail('文本不能超过 10000 字')
        if limits.min_length is not None and len(value) < limits.min_length:
            fail(f'至少填写 {limits.min_length} 字')
        if limits.max_length is not None and len(value) > limits.max_length:
            fail(f'最多填写 {limits.max_length} 字')
    elif kind == 'number':
        if not is_number(value):
            fail('请输入有限数值，且绝对值不能超过安全整数范围')
        if limits.integer_only and int(value) != value:
            fail('请输入整数')
        if limits.min_value is not None and value < limits.min_value:
            fail(f'数值不能小于 {limits.min_value:g}')
        if limits.max_value is not None and value > limits.max_value:
            fail(f'数值不能大于 {limits.max_value:g}')
        if int(value) == value:
            value = int(value)
    return value


def next_question(question: Question, value, following: str) -> str:
    target = question.routing.default_target
    if value is not None:
        for rule in question.routing.rules:
            op, expected = rule.operator, rule.value
            matched = (op == 'eq' and value == expected
                       or op == 'contains_any' and bool(set(value) & set(expected))
                       or op == 'contains_all' and set(expected).issubset(value)
                       or op == 'gt' and value > expected
                       or op == 'gte' and value >= expected
                       or op == 'lt' and value < expected
                       or op == 'lte' and value <= expected)
            if matched:
                target = rule.target
                break
    return following if target == 'NEXT' else target


def evaluate(definition: Definition, answers: list[Answer], stop_at: str | None = None):
    ids = [a.question_id for a in answers]
    duplicates = [qid for qid, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise BusinessError('DUPLICATE_ANSWER', '同一道题只能提交一个答案', question_id=duplicates[0])
    questions = {q.id: q for q in definition.questions}
    unknown = set(ids) - questions.keys()
    if unknown:
        raise BusinessError('UNKNOWN_QUESTION', '包含未知题目', question_id=sorted(unknown)[0])
    if not definition.questions:
        raise BusinessError('NO_QUESTIONS', '问卷没有题目')
    following = {q.id: definition.questions[i + 1].id if i + 1 < len(definition.questions) else 'END'
                 for i, q in enumerate(definition.questions)}
    raw = {a.question_id: a.value for a in answers}
    current, visited, normalized = definition.questions[0].id, [], []
    while current != 'END':
        if current in visited or current not in questions:
            raise BusinessError('INVALID_DEFINITION', '问卷跳转配置无效')
        question = questions[current]
        value = validate_answer(question, raw.get(current))
        visited.append(current)
        if value is not None:
            normalized.append({'question_id': current, 'value': value})
        target = next_question(question, value, following[current])
        if current == stop_at:
            break
        current = target
    if stop_at is not None and stop_at not in visited:
        raise BusinessError('INVALID_PROGRESS', '当前题目不在有效填写路径中', question_id=stop_at)
    extra = set(ids) - set(visited)
    if extra:
        raise BusinessError('OFF_PATH_ANSWER', '不能提交被跳过或尚未经过题目的答案', question_id=sorted(extra)[0])
    return normalized, visited, target
