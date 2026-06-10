from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ChildBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    qq_number: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value

    @field_validator("qq_number")
    @classmethod
    def validate_qq_number(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError("qq_number must contain digits only")
        return value


class ChildCreate(ChildBase):
    pass


class ChildUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    qq_number: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value

    @field_validator("qq_number")
    @classmethod
    def validate_qq_number(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError("qq_number must contain digits only")
        return value

    @model_validator(mode="after")
    def reject_null_updates(self) -> "ChildUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null")
        if "qq_number" in self.model_fields_set and self.qq_number is None:
            raise ValueError("qq_number must not be null")
        return self


class ChildRead(BaseModel):
    id: int
    name: str
    qq_number: str
    assignment_count: int
    last_reminded_at: str | None
    created_at: str
    updated_at: str


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: int
    title: str
    description: str = ""
    remind_at: datetime

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("remind_at", mode="before")
    @classmethod
    def parse_remind_at(cls, value: object) -> datetime:
        if not isinstance(value, str):
            raise ValueError("remind_at must be an ISO datetime")
        try:
            return datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError("remind_at must be an ISO datetime") from error

    @field_validator("remind_at")
    @classmethod
    def validate_remind_at(cls, value: datetime) -> datetime:
        now = datetime.now(value.tzinfo) if value.tzinfo else datetime.now()
        if value <= now:
            raise ValueError("remind_at must be in the future")
        return value


class AssignmentRead(BaseModel):
    id: int
    child_id: int
    child_name: str
    child_qq_number: str
    title: str
    description: str
    remind_at: str
    status: str
    created_at: str
    updated_at: str
