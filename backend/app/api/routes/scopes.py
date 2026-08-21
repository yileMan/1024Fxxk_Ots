from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.authorization import require_admin, require_current_user
from app.schemas.scopes import ScopeGrantRequest, ScopeResponse, ScopeSummaryResponse
from app.services.authentication import PublicUser
from app.services.scopes import ScopeAuthorizationError, ScopeInvalidError, ScopeTargetNotFoundError


router = APIRouter(tags=["product-scope-authorization"])


def _service(request: Request):
    return request.app.state.scope_authorization_service


def _raise_scope_error(error: ScopeAuthorizationError) -> None:
    if isinstance(error, ScopeTargetNotFoundError):
        raise HTTPException(404, detail={"code": error.code, "message": "授权目标不存在"}) from error
    if isinstance(error, ScopeInvalidError):
        raise HTTPException(422, detail={"code": error.code, "message": "产品范围不符合接口契约"}) from error
    raise error


@router.get("/users/{user_id}/scopes", response_model=ScopeSummaryResponse)
def list_user_scopes(
    user_id: int,
    request: Request,
    _admin: PublicUser = Depends(require_admin),
) -> ScopeSummaryResponse:
    try:
        return ScopeSummaryResponse(**asdict(_service(request).summary_for_user(user_id)))
    except ScopeAuthorizationError as error:
        _raise_scope_error(error)


@router.post("/users/{user_id}/scopes", response_model=ScopeResponse)
def grant_user_scope(
    user_id: int,
    payload: ScopeGrantRequest,
    request: Request,
    admin: PublicUser = Depends(require_admin),
) -> ScopeResponse:
    try:
        scope = _service(request).grant(actor_id=admin.id, user_id=user_id, **payload.model_dump())
        return ScopeResponse(**asdict(scope))
    except ScopeAuthorizationError as error:
        _raise_scope_error(error)


@router.delete("/users/{user_id}/scopes/{scope_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_user_scope(
    user_id: int,
    scope_id: int,
    request: Request,
    admin: PublicUser = Depends(require_admin),
) -> Response:
    try:
        _service(request).revoke(actor_id=admin.id, user_id=user_id, scope_id=scope_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ScopeAuthorizationError as error:
        _raise_scope_error(error)


@router.get("/scopes/me", response_model=ScopeSummaryResponse)
def current_scope_summary(
    request: Request,
    user: PublicUser = Depends(require_current_user),
) -> ScopeSummaryResponse:
    return ScopeSummaryResponse(**asdict(_service(request).summary_for_current_user(user)))
