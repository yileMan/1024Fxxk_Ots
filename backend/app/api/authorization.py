from fastapi import HTTPException, Request

from app.api.routes.authentication import COOKIE_NAME
from app.services.authentication import InvalidSessionError, PublicUser


def require_current_user(request: Request) -> PublicUser:
    user_id = request.cookies.get(COOKIE_NAME)
    if user_id is None:
        raise HTTPException(
            401,
            detail={"code": "AUTH_SESSION_INVALID", "message": "会话已失效"},
        )
    try:
        return request.app.state.authentication_service.current_user(user_id)
    except InvalidSessionError as error:
        raise HTTPException(
            401,
            detail={"code": "AUTH_SESSION_INVALID", "message": "会话已失效"},
        ) from error


def require_admin(request: Request) -> PublicUser:
    user = require_current_user(request)
    if "admin" not in user.roles:
        raise HTTPException(
            403,
            detail={"code": "AUTH_FORBIDDEN", "message": "无权执行管理员操作"},
        )
    return user
