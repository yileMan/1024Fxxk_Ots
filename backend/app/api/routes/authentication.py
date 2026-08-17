from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.schemas.authentication import LoginRequest, PublicUserResponse
from app.services.authentication import (
    AuthenticationService,
    DisabledUserError,
    InvalidCredentialsError,
    InvalidSessionError,
    PublicUser,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE_NAME = "ots_session"


def _response_user(user: PublicUser) -> dict[str, object]:
    return {"id": user.id, "login_name": user.login_name, "display_name": user.display_name, "roles": user.roles}


def _cookie_options(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {"httponly": True, "samesite": "lax", "secure": settings.cookie_secure, "path": "/"}


def _clear_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(COOKIE_NAME, **_cookie_options(request))


def _error(request: Request, status: int, code: str, message: str, clear_cookie: bool = False) -> JSONResponse:
    response = JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "correlation_id": getattr(request.state, "correlation_id", "generated-by-middleware")},
    )
    if clear_cookie:
        _clear_cookie(response, request)
    return response


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        return False
    expected = urlsplit(request.app.state.settings.allowed_origin)
    actual = urlsplit(origin)
    return (actual.scheme, actual.hostname, actual.port) == (expected.scheme, expected.hostname, expected.port)


def _require_origin(request: Request) -> JSONResponse | None:
    if _same_origin(request):
        return None
    return _error(request, 403, "AUTH_ORIGIN_REJECTED", "请求来源不受信任")


def _service(request: Request) -> AuthenticationService:
    return request.app.state.authentication_service


@router.post("/login", response_model=PublicUserResponse)
async def login(payload: LoginRequest, request: Request) -> JSONResponse:
    if origin_error := _require_origin(request):
        return origin_error
    try:
        user = _service(request).login(payload.login_name, payload.password)
    except InvalidCredentialsError:
        return _error(request, 401, "AUTH_INVALID_CREDENTIALS", "账号或密码错误")
    response = JSONResponse(_response_user(user))
    response.set_cookie(
        COOKIE_NAME,
        _service(request).create_session_token(user.id),
        max_age=2 * 60 * 60,
        **_cookie_options(request),
    )
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    if origin_error := _require_origin(request):
        return origin_error
    response = Response(status_code=204)
    _clear_cookie(response, request)
    return response


@router.get("/me", response_model=PublicUserResponse)
async def current_user(request: Request) -> JSONResponse:
    token = request.cookies.get(COOKIE_NAME)
    if token is None:
        return _error(request, 401, "AUTH_SESSION_INVALID", "会话已失效", clear_cookie=True)
    try:
        user = _service(request).current_user(token)
    except DisabledUserError:
        return _error(request, 403, "AUTH_USER_DISABLED", "账号已停用", clear_cookie=True)
    except InvalidSessionError:
        return _error(request, 401, "AUTH_SESSION_INVALID", "会话已失效", clear_cookie=True)
    return JSONResponse(_response_user(user))
