from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.schemas.authentication import LoginRequest, PublicUserResponse
from app.services.authentication import (
    AuthenticationService,
    InvalidCredentialsError,
    InvalidSessionError,
    PublicUser,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE_NAME = "ots_user_id"


def _response_user(user: PublicUser) -> dict[str, object]:
    return {"id": user.id, "login_name": user.login_name, "display_name": user.display_name, "roles": user.roles}


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "correlation_id": getattr(request.state, "correlation_id", "generated-by-middleware")},
    )


def _service(request: Request) -> AuthenticationService:
    return request.app.state.authentication_service


@router.post("/login", response_model=PublicUserResponse)
async def login(payload: LoginRequest, request: Request) -> JSONResponse:
    try:
        user = _service(request).login(payload.login_name, payload.password)
    except InvalidCredentialsError:
        return _error(request, 401, "AUTH_INVALID_CREDENTIALS", "账号或密码错误")
    response = JSONResponse(_response_user(user))
    response.set_cookie(COOKIE_NAME, str(user.id), path="/")
    return response


@router.get("/me", response_model=PublicUserResponse)
async def current_user(request: Request) -> JSONResponse:
    user_id = request.cookies.get(COOKIE_NAME)
    if user_id is None:
        return _error(request, 401, "AUTH_SESSION_INVALID", "会话已失效")
    try:
        user = _service(request).current_user(user_id)
    except InvalidSessionError:
        return _error(request, 401, "AUTH_SESSION_INVALID", "会话已失效")
    return JSONResponse(_response_user(user))


@router.post("/logout", status_code=204)
async def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
