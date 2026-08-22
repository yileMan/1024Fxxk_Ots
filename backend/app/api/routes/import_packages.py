from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile

from app.api.authorization import require_admin
from app.schemas.import_packages import ImportPackageResponse
from app.services.authentication import PublicUser
from app.services.import_packages import (
    ImportPackageErrorsNotAvailableError,
    ImportPackageNotFoundError,
    ImportPackageUploadTooLargeError,
)


router = APIRouter(tags=["package-contract-validation"])


def _service(request: Request):
    return request.app.state.import_package_service


def _not_found(error: ImportPackageNotFoundError) -> None:
    raise HTTPException(
        404,
        detail={"code": "PACKAGE_BATCH_NOT_FOUND", "message": "导入批次不存在"},
    ) from error


@router.post(
    "/import-packages/validate",
    response_model=ImportPackageResponse,
    status_code=201,
)
async def validate_import_package(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    admin: PublicUser = Depends(require_admin),
) -> ImportPackageResponse:
    try:
        result, created = await _service(request).validate_upload(file, admin.id)
    except ImportPackageUploadTooLargeError as error:
        raise HTTPException(
            413,
            detail={"code": "PACKAGE_TOO_LARGE", "message": "上传文件超过大小限制"},
        ) from error
    response.status_code = 201 if created else 200
    return ImportPackageResponse.model_validate(result)


@router.get("/import-packages/{batch_id}", response_model=ImportPackageResponse)
def get_import_package(
    batch_id: int,
    request: Request,
    _admin: PublicUser = Depends(require_admin),
) -> ImportPackageResponse:
    try:
        return ImportPackageResponse.model_validate(_service(request).get(batch_id))
    except ImportPackageNotFoundError as error:
        _not_found(error)


@router.get(
    "/import-packages/{batch_id}/errors",
    response_class=Response,
    responses={
        200: {
            "description": "数据包校验错误清单",
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def download_import_package_errors(
    batch_id: int,
    request: Request,
    _admin: PublicUser = Depends(require_admin),
) -> Response:
    try:
        content = _service(request).error_file(batch_id)
    except ImportPackageNotFoundError as error:
        _not_found(error)
    except ImportPackageErrorsNotAvailableError as error:
        raise HTTPException(
            409,
            detail={
                "code": "PACKAGE_ERRORS_NOT_AVAILABLE",
                "message": "当前批次没有可下载的校验错误",
            },
        ) from error
    return Response(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="package_validation_errors.csv"'},
    )
