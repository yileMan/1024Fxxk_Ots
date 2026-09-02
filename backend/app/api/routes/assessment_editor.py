from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.authorization import require_current_user
from app.schemas.assessment_editor import AssessmentDetailResponse, AssessmentDraftUpdateRequest
from app.services.assessment_editor import (
    AssessmentEditorError,
    AssessmentForbiddenError,
    AssessmentNotEditableError,
    AssessmentNotFoundError,
    AssessmentValidationError,
    CvssSourceUnavailableError,
    AssessmentVersionConflictError,
)
from app.services.authentication import PublicUser


router = APIRouter(tags=["assessment-editor-core"])


def _service(request: Request):
    return request.app.state.assessment_editor_service


def _raise_error(error: AssessmentEditorError) -> None:
    if isinstance(error, AssessmentNotFoundError):
        raise HTTPException(
            404, detail={"code": error.code, "message": "产品评估不存在"}
        ) from error
    if isinstance(error, AssessmentForbiddenError):
        raise HTTPException(
            403, detail={"code": error.code, "message": "无权访问或编辑该产品评估"}
        ) from error
    if isinstance(error, AssessmentValidationError):
        raise HTTPException(
            422,
            detail={
                "code": error.code,
                "message": "来源 CVSS v3.1 不可用"
                if isinstance(error, CvssSourceUnavailableError)
                else "评估草稿校验失败",
                "fields": error.fields,
            },
        ) from error
    if isinstance(error, (AssessmentNotEditableError, AssessmentVersionConflictError)):
        message = "评估当前不可编辑" if isinstance(error, AssessmentNotEditableError) else "评估已被其他操作更新，请刷新"
        raise HTTPException(409, detail={"code": error.code, "message": message}) from error
    raise error


ERROR_RESPONSES = {
    403: {"description": "无权访问或编辑"},
    404: {"description": "评估不存在"},
    409: {"description": "评估不可编辑或版本冲突"},
    422: {"description": "草稿字段校验失败"},
}


@router.get(
    "/assessments/{assessment_id}",
    response_model=AssessmentDetailResponse,
    responses=ERROR_RESPONSES,
)
def assessment_detail(
    assessment_id: int,
    request: Request,
    user: PublicUser = Depends(require_current_user),
) -> AssessmentDetailResponse:
    try:
        return AssessmentDetailResponse.model_validate(
            _service(request).detail(user, assessment_id)
        )
    except AssessmentEditorError as error:
        _raise_error(error)


@router.put(
    "/assessments/{assessment_id}/draft",
    response_model=AssessmentDetailResponse,
    responses=ERROR_RESPONSES,
)
def save_assessment_draft(
    assessment_id: int,
    payload: AssessmentDraftUpdateRequest,
    request: Request,
    user: PublicUser = Depends(require_current_user),
) -> AssessmentDetailResponse:
    try:
        return AssessmentDetailResponse.model_validate(
            _service(request).save_draft(user, assessment_id, payload)
        )
    except AssessmentEditorError as error:
        _raise_error(error)
