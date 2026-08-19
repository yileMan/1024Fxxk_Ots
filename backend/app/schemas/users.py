from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


Role = Literal["admin", "product_owner", "reviewer"]


class UserCreateRequest(BaseModel):
    login_name: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=100)
    password: str
    roles: list[Role] = Field(min_length=1)

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, roles: list[Role]) -> list[Role]:
        return list(dict.fromkeys(roles))


class UserUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    roles: list[Role] = Field(min_length=1)
    row_version: int = Field(ge=1)

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, roles: list[Role]) -> list[Role]:
        return list(dict.fromkeys(roles))


class PasswordResetRequest(BaseModel):
    password: str
    row_version: int = Field(ge=1)


class UserDisableRequest(BaseModel):
    row_version: int = Field(ge=1)


class UserResponse(BaseModel):
    id: int
    login_name: str
    display_name: str
    roles: list[Role]
    status: Literal["active", "disabled"]
    last_login_at: datetime | None
    row_version: int
    created_at: datetime
    updated_at: datetime


class UserPageResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
