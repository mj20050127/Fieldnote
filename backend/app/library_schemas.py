from datetime import datetime
from typing import Literal

from pydantic import Field

from .schemas import AnswerValue, Model, OptionStatistic, QuestionContent, QuestionSource, RevisionInput


class BankInput(Model):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=1000)


class BankUpdate(RevisionInput):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    archived: bool | None = None


class BankOut(BankInput):
    id: str
    archived: bool
    revision: int
    created_at: datetime
    updated_at: datetime


class BankList(Model):
    items: list[BankOut]


class Operation(Model):
    request_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{16,100}$')


class LibraryCreate(Operation):
    bank_id: str
    content: QuestionContent


class VersionCreate(Operation):
    parent_version_id: str
    content: QuestionContent


class ForkInput(LibraryCreate):
    source_version_id: str


class RestoreInput(Operation):
    target_version_id: str
    parent_version_id: str


class LibraryUpdate(RevisionInput):
    bank_id: str | None = None
    archived: bool | None = None


class VersionOut(Model):
    id: str
    question_id: str
    version_no: int
    parent_version_id: str | None
    restored_from_version_id: str | None
    content: QuestionContent
    created_by: str
    created_at: datetime


class VersionList(Model):
    items: list[VersionOut]
    total: int
    page: int
    page_size: int


class LibraryQuestionOut(Model):
    id: str
    owner_id: str
    owner_username: str
    bank_id: str
    archived: bool
    revision: int
    access: Literal['owner', 'shared', 'historical']
    available_for_reuse: bool
    derived_from: QuestionSource | None
    latest_version: VersionOut
    created_at: datetime
    updated_at: datetime


class LibraryQuestionList(Model):
    items: list[LibraryQuestionOut]
    total: int
    page: int
    page_size: int


class ShareInput(RevisionInput):
    username: str = Field(min_length=3, max_length=32)


class SharedUser(Model):
    id: str
    username: str


class SharesOut(Model):
    items: list[SharedUser]
    revision: int


class UsageSlot(Model):
    instance_id: str
    version_id: str


class Usage(Model):
    survey_id: str
    title: str
    status: str
    slots: list[UsageSlot]


class UsageList(Model):
    items: list[Usage]
    total: int
    page: int
    page_size: int


class Frequency(Model):
    value: float
    count: int


class VersionStatistics(Model):
    version: VersionOut
    survey_count: int
    response_count: int
    occurrence_count: int
    reached_count: int
    answered_count: int
    skipped_count: int
    unanswered_count: int
    average: float | None
    minimum: float | None
    maximum: float | None
    options: list[OptionStatistic]
    values: list[AnswerValue]
    frequencies: list[Frequency]
    frequency_total: int
    page: int
    page_size: int


class LibraryStatistics(Model):
    question_id: str
    groups: list[VersionStatistics]
