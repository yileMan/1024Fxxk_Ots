from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.routes.authentication import COOKIE_NAME
from app.schemas.users import (
    PasswordResetRequest,
    Role,
    UserCreateRequest,
    UserDisableRequest,
    UserPageResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.authentication import InvalidSessionError, PublicUser
from app.services.users import (
    UserLoginNameConflictError,
    UserManagementError,
    UserManagementService,
    UserNotFoundError,
    UserVersionConflictError,
)

router = APIRouter(prefix="/users", tags=["user-administration"])


def _detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def require_admin(request: Request) -> PublicUser:
    user_id = request.cookies.get(COOKIE_NAME)
    if user_id is None:
        raise HTTPException(401, detail=_detail("AUTH_SESSION_INVALID", "会话已失效"))
    try:
        user = request.app.state.authentication_service.current_user(user_id)
    except InvalidSessionError as error:
        raise HTTPException(401, detail=_detail("AUTH_SESSION_INVALID", "会话已失效")) from error
    if "admin" not in user.roles:
        raise HTTPException(403, detail=_detail("AUTH_FORBIDDEN", "无权访问用户管理"))
    return user


def _service(request: Request) -> UserManagementService:
    return request.app.state.user_management_service


def _raise_user_error(error: UserManagementError) -> None:
    if isinstance(error, UserNotFoundError):
        raise HTTPException(404, detail=_detail(error.code, "用户不存在")) from error
    if isinstance(error, UserLoginNameConflictError):
        raise HTTPException(409, detail=_detail(error.code, "登录名已存在")) from error
    if isinstance(error, UserVersionConflictError):
        raise HTTPException(409, detail=_detail(error.code, "数据已被其他管理员更新")) from error
    raise error


@router.get("", response_model=UserPageResponse)
def list_users(
    request: Request,
    _admin: PublicUser = Depends(require_admin),
    query: str | None = None,
    status_filter: Literal["active", "disabled"] | None = Query(None, alias="status"),
    role: Role | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> UserPageResponse:
    result = _service(request).list_users(
        query=query,
        status=status_filter,
        role=role,
        page=page,
        page_size=page_size,
    )
    return UserPageResponse(**asdict(result))


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    request: Request,
    _admin: PublicUser = Depends(require_admin),
) -> UserResponse:
    try:
        return UserResponse(**asdict(_service(request).get_user(user_id)))
    except UserManagementError as error:
        _raise_user_error(error)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    admin: PublicUser = Depends(require_admin),
) -> UserResponse:
    try:
        user = _service(request).create_user(actor_id=admin.id, **payload.model_dump())
        return UserResponse(**asdict(user))
    except UserManagementError as error:
        _raise_user_error(error)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    admin: PublicUser = Depends(require_admin),
) -> UserResponse:
    try:
        user = _service(request).update_user(actor_id=admin.id, user_id=user_id, **payload.model_dump())
        return UserResponse(**asdict(user))
    except UserManagementError as error:
        _raise_user_error(error)


@router.post("/{user_id}/reset-password", response_model=UserResponse)
def reset_password(
    user_id: int,
    payload: PasswordResetRequest,
    request: Request,
    admin: PublicUser = Depends(require_admin),
) -> UserResponse:
    try:
        user = _service(request).reset_password(actor_id=admin.id, user_id=user_id, **payload.model_dump())
        return UserResponse(**asdict(user))
    except UserManagementError as error:
        _raise_user_error(error)


@router.post("/{user_id}/disable", response_model=UserResponse)
def disable_user(
    user_id: int,
    payload: UserDisableRequest,
    request: Request,
    admin: PublicUser = Depends(require_admin),
) -> UserResponse:
    try:
        user = _service(request).disable_user(actor_id=admin.id, user_id=user_id, **payload.model_dump())
        return UserResponse(**asdict(user))
    except UserManagementError as error:
        _raise_user_error(error)
