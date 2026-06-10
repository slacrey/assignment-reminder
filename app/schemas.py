import re

from pydantic import BaseModel, field_validator, model_validator


class ChildBase(BaseModel):
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
