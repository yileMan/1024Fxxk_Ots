from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.authorization import require_current_user
from app.schemas.assessment_editor import (
    AssessmentActionRequest,
    AssessmentDetailResponse,
    AssessmentDraftUpdateRequest,
    AssessmentRevisionComparisonResponse,
    AssessmentRevisionCreateRequest,
    AssessmentRevisionHistoryResponse,
    AssessmentReturnRequest,
    AssessmentReturnResponse,
)
from app.services.assessment_editor import (
    AssessmentEditorError,
    AssessmentForbiddenError,
    AssessmentNotEditableError,
    AssessmentNotFoundError,
    AssessmentValidationError,
    CvssSourceUnavailableError,
    AssessmentVersionConflictError,
    AssessmentActionConflictError,
    ReviewerReassignmentRequiredError,
    AssessmentSelfReviewError,
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
        message = "禁止审核自己提交的评估" if isinstance(error, AssessmentSelfReviewError) else "无权访问或编辑该产品评估"
        raise HTTPException(
            403, detail={"code": error.code, "message": message}
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
    if isinstance(error, (AssessmentNotEditableError, AssessmentVersionConflictError, AssessmentActionConflictError, ReviewerReassignmentRequiredError)):
        if isinstance(error, ReviewerReassignmentRequiredError):
            message = "提交人与当前审核人相同，请先重新分配审核人"
        elif isinstance(error, AssessmentNotEditableError):
            message = "评估当前不可编辑"
        else:
            message = "评估已被其他操作更新，请刷新"
        detail = {"code": error.code, "message": message}
        if isinstance(error, AssessmentNotEditableError) and error.current_revision_id is not None:
            detail["current_revision_id"] = error.current_revision_id
        raise HTTPException(409, detail=detail) from error
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


@router.post(
    "/assessments/{assessment_id}/submit",
    response_model=AssessmentDetailResponse,
    responses=ERROR_RESPONSES,
)
def submit_assessment(
    assessment_id: int, payload: AssessmentActionRequest, request: Request,
    user: PublicUser = Depends(require_current_user),
) -> AssessmentDetailResponse:
    try:
        return AssessmentDetailResponse.model_validate(
            _service(request).submit(user, assessment_id, payload)
        )
    except AssessmentEditorError as error:
        _raise_error(error)


@router.post(
    "/assessments/{assessment_id}/approve",
    response_model=AssessmentDetailResponse,
    responses=ERROR_RESPONSES,
)
def approve_assessment(
    assessment_id: int, payload: AssessmentActionRequest, request: Request,
    user: PublicUser = Depends(require_current_user),
) -> AssessmentDetailResponse:
    try:
        return AssessmentDetailResponse.model_validate(
            _service(request).approve(user, assessment_id, payload)
        )
    except AssessmentEditorError as error:
        _raise_error(error)


@router.post(
    "/assessments/{assessment_id}/return",
    response_model=AssessmentReturnResponse,
    responses=ERROR_RESPONSES,
)
def return_assessment(
    assessment_id: int, payload: AssessmentReturnRequest, request: Request,
    user: PublicUser = Depends(require_current_user),
) -> AssessmentReturnResponse:
    try:
        return AssessmentReturnResponse.model_validate(
            _service(request).return_assessment(user, assessment_id, payload)
        )
    except AssessmentEditorError as error:
        _raise_error(error)


@router.post(
    "/assessments/{assessment_id}/revisions",
    response_model=AssessmentDetailResponse,
    responses=ERROR_RESPONSES,
)
def create_assessment_revision(
    assessment_id: int,
    payload: AssessmentRevisionCreateRequest,
    request: Request,
    user: PublicUser = Depends(require_current_user),
) -> AssessmentDetailResponse:
    try:
        return AssessmentDetailResponse.model_validate(
            _service(request).create_revision(user, assessment_id, payload)
        )
    except AssessmentEditorError as error:
        _raise_error(error)


@router.get(
    "/assessments/{assessment_id}/revisions",
    response_model=AssessmentRevisionHistoryResponse,
    responses=ERROR_RESPONSES,
)
def assessment_revision_history(
    assessment_id: int,
    request: Request,
    user: PublicUser = Depends(require_current_user),
) -> AssessmentRevisionHistoryResponse:
    try:
        return AssessmentRevisionHistoryResponse.model_validate(
            _service(request).revision_history(user, assessment_id)
        )
    except AssessmentEditorError as error:
        _raise_error(error)


@router.get(
    "/assessments/{assessment_id}/revision-comparison",
    response_model=AssessmentRevisionComparisonResponse,
    responses=ERROR_RESPONSES,
)
def compare_assessment_revisions(
    assessment_id: int,
    base_revision_id: int,
    target_revision_id: int,
    request: Request,
    user: PublicUser = Depends(require_current_user),
) -> AssessmentRevisionComparisonResponse:
    try:
        return AssessmentRevisionComparisonResponse.model_validate(
            _service(request).compare_revisions(
                user, assessment_id, base_revision_id, target_revision_id
            )
        )
    except AssessmentEditorError as error:
        _raise_error(error)
