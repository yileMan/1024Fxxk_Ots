from pydantic import BaseModel


class LoginRequest(BaseModel):
    login_name: str
    password: str


class PublicUserResponse(BaseModel):
    id: int
    login_name: str
    display_name: str
    roles: list[str]
