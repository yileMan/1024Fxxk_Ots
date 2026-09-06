from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.authorization import require_current_user
from app.schemas.assessment_export import AssessmentExportPreviewResponse
from app.services.assessment_export import (
    AssessmentExportEmptyError,
    AssessmentExportError,
    AssessmentExportForbiddenError,
    AssessmentExportScopeNotFoundError,
)
from app.services.authentication import PublicUser


router = APIRouter(prefix="/assessment-exports", tags=["assessment-export"])


def _service(request: Request):
    return request.app.state.assessment_export_service


def _error(error: AssessmentExportError) -> None:
    if isinstance(error, AssessmentExportForbiddenError):
        raise HTTPException(403, detail={"code": error.code, "message": "无权导出该产品版本"}) from error
    if isinstance(error, AssessmentExportScopeNotFoundError):
        raise HTTPException(404, detail={"code": error.code, "message": "产品版本或 OTS 关联不存在"}) from error
    if isinstance(error, AssessmentExportEmptyError):
        raise HTTPException(409, detail={"code": error.code, "message": "当前范围没有可导出的评估"}) from error
    raise error


@router.get("/preview", response_model=AssessmentExportPreviewResponse)
def preview_export(
    request: Request,
    product_version_id: int = Query(ge=1),
    ots_id: int = Query(ge=1),
    user: PublicUser = Depends(require_current_user),
) -> AssessmentExportPreviewResponse:
    try:
        return AssessmentExportPreviewResponse.model_validate(
            _service(request).preview(user, product_version_id, ots_id), from_attributes=True,
        )
    except AssessmentExportError as error:
        _error(error)


@router.get("/csv", response_class=StreamingResponse, responses={200: {"content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}}})
def download_export(
    request: Request,
    product_version_id: int = Query(ge=1),
    ots_id: int = Query(ge=1),
    user: PublicUser = Depends(require_current_user),
) -> StreamingResponse:
    try:
        result = _service(request).export_csv(user, product_version_id, ots_id)
    except AssessmentExportError as error:
        _error(error)
    return StreamingResponse(
        result.chunks, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{result.file_name}"'},
    )
