from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.routes.users import require_admin
from app.schemas.products import DisableRequest, ProductCreateRequest, ProductPageResponse, ProductResponse, ProductVersionResponse, ProductUpdateRequest, VersionCreateRequest, VersionUpdateRequest
from app.services.authentication import PublicUser
from app.services.products import ProductAssignmentInvalidError, ProductCodeConflictError, ProductManagementError, ProductNotFoundError, ProductVersionConflictError

router = APIRouter(prefix="/products", tags=["product-version-management"])


def _service(request: Request):
    return request.app.state.product_management_service


def _error(error: ProductManagementError) -> None:
    if isinstance(error, ProductNotFoundError):
        raise HTTPException(404, detail={"code": error.code, "message": "产品或版本不存在"}) from error
    if isinstance(error, (ProductCodeConflictError, ProductVersionConflictError)):
        raise HTTPException(409, detail={"code": error.code, "message": "产品编号或版本号已存在，或数据已变化"}) from error
    if isinstance(error, ProductAssignmentInvalidError):
        raise HTTPException(422, detail={"code": error.code, "message": "负责人或审核人不符合资格"}) from error
    raise error


@router.get("", response_model=ProductPageResponse)
def list_products(request: Request, _admin: PublicUser = Depends(require_admin), query: str | None = None, status_filter: Literal["active", "disabled"] | None = Query(None, alias="status"), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> ProductPageResponse:
    result = _service(request).list_products(query=query, status=status_filter, page=page, page_size=page_size)
    return ProductPageResponse(items=[ProductResponse.model_validate(item, from_attributes=True) for item in result.items], total=result.total, page=result.page, page_size=result.page_size)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreateRequest, request: Request, admin: PublicUser = Depends(require_admin)) -> ProductResponse:
    try:
        return ProductResponse.model_validate(_service(request).create_product(actor_id=admin.id, **payload.model_dump()), from_attributes=True)
    except ProductManagementError as error:
        _error(error)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, request: Request, _admin: PublicUser = Depends(require_admin)) -> ProductResponse:
    try:
        return ProductResponse.model_validate(_service(request).get_product(product_id), from_attributes=True)
    except ProductManagementError as error:
        _error(error)


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, payload: ProductUpdateRequest, request: Request, admin: PublicUser = Depends(require_admin)) -> ProductResponse:
    try:
        return ProductResponse.model_validate(_service(request).update_product(actor_id=admin.id, product_id=product_id, **payload.model_dump()), from_attributes=True)
    except ProductManagementError as error:
        _error(error)


@router.post("/{product_id}/disable", response_model=ProductResponse)
def disable_product(product_id: int, payload: DisableRequest, request: Request, admin: PublicUser = Depends(require_admin)) -> ProductResponse:
    try:
        return ProductResponse.model_validate(_service(request).disable_product(actor_id=admin.id, product_id=product_id, **payload.model_dump()), from_attributes=True)
    except ProductManagementError as error:
        _error(error)


@router.get("/{product_id}/versions", response_model=list[ProductVersionResponse])
def list_versions(product_id: int, request: Request, _admin: PublicUser = Depends(require_admin)) -> list[ProductVersionResponse]:
    try:
        return [ProductVersionResponse.model_validate(item, from_attributes=True) for item in _service(request).list_versions(product_id)]
    except ProductManagementError as error:
        _error(error)


@router.post("/{product_id}/versions", response_model=ProductVersionResponse, status_code=status.HTTP_201_CREATED)
def create_version(product_id: int, payload: VersionCreateRequest, request: Request, admin: PublicUser = Depends(require_admin)) -> ProductVersionResponse:
    try:
        return ProductVersionResponse.model_validate(_service(request).create_version(actor_id=admin.id, product_id=product_id, **payload.model_dump()), from_attributes=True)
    except ProductManagementError as error:
        _error(error)


@router.get("/{product_id}/versions/{version_id}", response_model=ProductVersionResponse)
def get_version(product_id: int, version_id: int, request: Request, _admin: PublicUser = Depends(require_admin)) -> ProductVersionResponse:
    try:
        return ProductVersionResponse.model_validate(_service(request).get_version(product_id, version_id), from_attributes=True)
    except ProductManagementError as error:
        _error(error)


@router.put("/{product_id}/versions/{version_id}", response_model=ProductVersionResponse)
def update_version(product_id: int, version_id: int, payload: VersionUpdateRequest, request: Request, admin: PublicUser = Depends(require_admin)) -> ProductVersionResponse:
    try:
        return ProductVersionResponse.model_validate(_service(request).update_version(actor_id=admin.id, product_id=product_id, version_id=version_id, **payload.model_dump()), from_attributes=True)
    except ProductManagementError as error:
        _error(error)


@router.post("/{product_id}/versions/{version_id}/disable", response_model=ProductVersionResponse)
def disable_version(product_id: int, version_id: int, payload: DisableRequest, request: Request, admin: PublicUser = Depends(require_admin)) -> ProductVersionResponse:
    try:
        return ProductVersionResponse.model_validate(_service(request).disable_version(actor_id=admin.id, product_id=product_id, version_id=version_id, **payload.model_dump()), from_attributes=True)
    except ProductManagementError as error:
        _error(error)
