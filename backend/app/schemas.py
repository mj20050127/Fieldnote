from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Identifier = str


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', json_schema_serialization_defaults_required=True)


class Credentials(Model):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class UserMe(Model):
    id: str
    username: str
    csrf_token: str


class Option(Model):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    text: str = Field(max_length=200)


class Validation(Model):
    min_choices: int | None = Field(default=None, ge=0, le=50)
    max_choices: int | None = Field(default=None, ge=0, le=50)
    min_length: int | None = Field(default=None, ge=0, le=10000)
    max_length: int | None = Field(default=None, ge=0, le=10000)
    min_value: float | None = Field(default=None, allow_inf_nan=False)
    max_value: float | None = Field(default=None, allow_inf_nan=False)
    integer_only: bool = False


class Rule(Model):
    operator: Literal['eq', 'contains_any', 'contains_all', 'gt', 'gte', 'lt', 'lte']
    value: Any
    target: str = Field(min_length=1, max_length=80)


class Routing(Model):
    rules: list[Rule] = Field(default_factory=list, max_length=20)
    default_target: str = Field(default='NEXT', max_length=80)


class QuestionContent(Model):
    type: Literal['single_choice', 'multiple_choice', 'text', 'number']
    title: str = Field(default='', max_length=500)
    description: str = Field(default='', max_length=1000)
    required: bool = True
    options: list[Option] = Field(default_factory=list, max_length=50)
    validation: Validation = Field(default_factory=Validation)


class QuestionSource(Model):
    question_id: str = Field(min_length=1, max_length=80)
    version_id: str = Field(min_length=1, max_length=80)


class Question(QuestionContent):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    routing: Routing = Field(default_factory=Routing)
    source: QuestionSource | None = None


class SurveySettings(Model):
    allow_anonymous: bool = True
    allow_multiple: bool = False


class Definition(Model):
    title: str = Field(default='未命名问卷', min_length=1, max_length=120)
    description: str = Field(default='', max_length=3000)
    settings: SurveySettings = Field(default_factory=SurveySettings)
    questions: list[Question] = Field(default_factory=list, max_length=100)


class DraftUpdate(Definition):
    expected_revision: int = Field(ge=1)


class RevisionInput(Model):
    expected_revision: int = Field(ge=1)


class ManagementUpdate(RevisionInput):
    deadline: datetime | None = None

    @field_validator('deadline')
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError('截止时间必须包含时区')
        return value


class SurveyOut(Definition):
    id: str
    public_code: str
    status: Literal['draft', 'published', 'closed']
    effective_status: Literal['draft', 'published', 'closed', 'expired']
    deadline: datetime | None
    revision: int
    definition_version: int
    schema_version: int
    created_at: datetime
    updated_at: datetime
    response_count: int = 0


class FormOut(Definition):
    public_code: str
    definition_version: int
    deadline: datetime | None
    effective_status: Literal['draft', 'published', 'closed', 'expired']
    already_submitted: bool = False


class Answer(Model):
    question_id: str = Field(max_length=80)
    value: Any


class EvaluateInput(Model):
    current_question_id: str = Field(max_length=80)
    answers: list[Answer] = Field(default_factory=list, max_length=100)


class EvaluateOut(Model):
    visited_question_ids: list[str]
    next_question_id: str


class Submission(Model):
    request_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{16,100}$')
    definition_version: int = Field(ge=1)
    is_anonymous: bool = True
    answers: list[Answer] = Field(default_factory=list, max_length=100)


class Receipt(Model):
    id: str
    submitted_at: datetime
    replayed: bool = False


class Issue(Model):
    code: str
    message: str
    question_id: str | None = None
    field: str | None = None


class DefinitionCheck(Model):
    valid: bool
    errors: list[Issue]
    warnings: list[Issue]


class ResponseOut(Model):
    id: str
    definition_version: int
    is_anonymous: bool
    respondent: str | None
    answers: list[Answer]
    visited_question_ids: list[str]
    submitted_at: datetime


class SurveyList(Model):
    items: list[SurveyOut]
    total: int
    page: int
    page_size: int


class ResponseList(Model):
    items: list[ResponseOut]
    total: int
    page: int
    page_size: int


class OptionStatistic(Option):
    count: int
    percentage: float


class QuestionStatistic(Model):
    question_id: str
    title: str
    type: str
    answered_count: int
    reached_count: int
    skipped_count: int
    unanswered_count: int
    average: float | None
    options: list[OptionStatistic]


class Statistics(Model):
    total_responses: int
    questions: list[QuestionStatistic]


class AnswerValue(Model):
    value: Any
    submitted_at: datetime


class QuestionStatistics(QuestionStatistic):
    values: list[AnswerValue]
    page: int
    page_size: int
    total: int


class Overview(Model):
    total_surveys: int
    total_responses: int
    published: int
    draft: int

