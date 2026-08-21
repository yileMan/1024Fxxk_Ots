from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response, status

from app.api.authorization import require_admin, require_current_user
from app.schemas.ots import CsvImportResultResponse, OtsCreateRequest, OtsPageResponse, OtsProductVersionResponse, OtsResponse, OtsUpdateRequest, ProductOtsCreateRequest, ProductOtsResponse
from app.services.authentication import PublicUser
from app.services.ots import OtsConflictError, OtsCsvInvalidError, OtsManagementError, OtsNotFoundError, OtsVersionConflictError, ProductOtsConflictError, ProductOtsHistoryConflictError
from app.services.scopes import ProductScopeForbiddenError, ScopeTargetNotFoundError

router = APIRouter(tags=["ots-bom-management"])


def _service(request: Request):
    return request.app.state.ots_management_service


def _error(error: OtsManagementError) -> None:
    if isinstance(error, OtsNotFoundError):
        raise HTTPException(404, detail={"code": error.code, "message": "OTS、产品版本或关联不存在"}) from error
    if isinstance(error, OtsCsvInvalidError):
        raise HTTPException(422, detail={"code": error.code, "message": "CSV 校验失败", "errors": error.errors}) from error
    if isinstance(error, OtsVersionConflictError):
        raise HTTPException(409, detail={"code": error.code, "message": "OTS 数据已被其他管理员更新"}) from error
    if isinstance(error, ProductOtsHistoryConflictError):
        raise HTTPException(409, detail={"code": error.code, "message": "关联已有下游历史，不能移除"}) from error
    if isinstance(error, (OtsConflictError, ProductOtsConflictError)):
        raise HTTPException(409, detail={"code": error.code, "message": "OTS 或产品清单关联已存在"}) from error
    raise error


@router.get("/ots-components", response_model=OtsPageResponse)
def list_ots(request: Request, _admin: PublicUser = Depends(require_admin), query: str | None = None, is_eol: bool | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> OtsPageResponse:
    result = _service(request).list_ots(query=query, is_eol=is_eol, page=page, page_size=page_size)
    return OtsPageResponse(items=[OtsResponse.model_validate(item, from_attributes=True) for item in result.items], total=result.total, page=result.page, page_size=result.page_size)


@router.post("/ots-components", response_model=OtsResponse, status_code=status.HTTP_201_CREATED)
def create_ots(payload: OtsCreateRequest, request: Request, admin: PublicUser = Depends(require_admin)) -> OtsResponse:
    try:
        return OtsResponse.model_validate(_service(request).create_ots(actor_id=admin.id, **payload.model_dump()), from_attributes=True)
    except OtsManagementError as error:
        _error(error)


@router.get("/ots-components/{ots_id}", response_model=OtsResponse)
def get_ots(ots_id: int, request: Request, _admin: PublicUser = Depends(require_admin)) -> OtsResponse:
    try:
        return OtsResponse.model_validate(_service(request).get_ots(ots_id), from_attributes=True)
    except OtsManagementError as error:
        _error(error)


@router.put("/ots-components/{ots_id}", response_model=OtsResponse)
def update_ots(ots_id: int, payload: OtsUpdateRequest, request: Request, admin: PublicUser = Depends(require_admin)) -> OtsResponse:
    try:
        return OtsResponse.model_validate(_service(request).update_ots(actor_id=admin.id, ots_id=ots_id, **payload.model_dump()), from_attributes=True)
    except OtsManagementError as error:
        _error(error)


@router.get("/ots-components/{ots_id}/product-versions", response_model=list[OtsProductVersionResponse])
def associated_versions(ots_id: int, request: Request, _admin: PublicUser = Depends(require_admin)) -> list[OtsProductVersionResponse]:
    try:
        return [OtsProductVersionResponse.model_validate(item, from_attributes=True) for item in _service(request).list_associated_versions(ots_id)]
    except OtsManagementError as error:
        _error(error)


@router.get("/product-versions/{version_id}/ots", response_model=list[ProductOtsResponse])
def list_product_ots(version_id: int, request: Request, user: PublicUser = Depends(require_current_user)) -> list[ProductOtsResponse]:
    try:
        request.app.state.scope_authorization_service.require_version_access(user, version_id)
        return [ProductOtsResponse.model_validate(item, from_attributes=True) for item in _service(request).list_product_ots(version_id)]
    except ProductScopeForbiddenError as error:
        raise HTTPException(403, detail={"code": error.code, "message": "无权访问该产品版本"}) from error
    except ScopeTargetNotFoundError as error:
        raise HTTPException(404, detail={"code": error.code, "message": "产品版本不存在"}) from error
    except OtsManagementError as error:
        _error(error)


@router.post("/product-versions/{version_id}/ots", response_model=ProductOtsResponse, status_code=status.HTTP_201_CREATED)
def create_product_ots(version_id: int, payload: ProductOtsCreateRequest, request: Request, admin: PublicUser = Depends(require_admin)) -> ProductOtsResponse:
    try:
        return ProductOtsResponse.model_validate(_service(request).create_relation(actor_id=admin.id, version_id=version_id, ots_component_id=payload.ots_component_id), from_attributes=True)
    except OtsManagementError as error:
        _error(error)


@router.delete("/product-versions/{version_id}/ots/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_product_ots(version_id: int, relation_id: int, request: Request, admin: PublicUser = Depends(require_admin)) -> Response:
    try:
        _service(request).remove_relation(actor_id=admin.id, version_id=version_id, relation_id=relation_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except OtsManagementError as error:
        _error(error)


@router.get("/product-ots/template")
def product_ots_template(request: Request, _admin: PublicUser = Depends(require_admin)) -> Response:
    return Response(_service(request).template_csv(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="product-ots-template.csv"'})


@router.get("/product-versions/{version_id}/ots/export")
def export_product_ots(version_id: int, request: Request, _admin: PublicUser = Depends(require_admin)) -> Response:
    try:
        return Response(_service(request).export_csv(version_id), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="product-version-{version_id}-ots.csv"'})
    except OtsManagementError as error:
        _error(error)


@router.post("/product-versions/{version_id}/ots/import", response_model=CsvImportResultResponse)
def import_product_ots(version_id: int, request: Request, content: bytes = Body(media_type="text/csv"), file_name: str = Header("product-ots.csv", alias="X-File-Name"), admin: PublicUser = Depends(require_admin)) -> CsvImportResultResponse:
    try:
        return CsvImportResultResponse.model_validate(_service(request).import_csv(actor_id=admin.id, version_id=version_id, content=content, file_name=file_name), from_attributes=True)
    except OtsManagementError as error:
        _error(error)
