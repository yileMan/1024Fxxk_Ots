from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.authorization import require_admin
from app.schemas.collector_scope import CollectorScopePreviewResponse
from app.services.authentication import PublicUser
from app.services.collector_scope import CollectorScopeHistoryInvalidError


router = APIRouter(tags=["collector-scope-export"])


def _service(request: Request):
    return request.app.state.collector_scope_service


def _history_error(error: CollectorScopeHistoryInvalidError) -> None:
    raise HTTPException(
        500,
        detail={
            "code": error.code,
            "message": "成功批次中的采集范围历史无效，请联系管理员检查数据",
        },
    ) from error


@router.get("/collector-scope", response_model=CollectorScopePreviewResponse)
def preview_collector_scope(
    request: Request,
    _admin: PublicUser = Depends(require_admin),
) -> CollectorScopePreviewResponse:
    try:
        return CollectorScopePreviewResponse.model_validate(
            _service(request).preview(),
            from_attributes=True,
        )
    except CollectorScopeHistoryInvalidError as error:
        _history_error(error)


@router.get(
    "/collector-scope/export",
    response_class=Response,
    responses={
        200: {
            "description": "规范采集范围 CSV",
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
            "headers": {
                "Content-Disposition": {"schema": {"type": "string"}},
                "X-Scope-Export-ID": {"schema": {"type": "string", "format": "uuid"}},
                "X-Content-SHA256": {"schema": {"type": "string"}},
            },
        }
    },
)
def export_collector_scope(
    request: Request,
    _admin: PublicUser = Depends(require_admin),
) -> Response:
    try:
        result = _service(request).export()
    except CollectorScopeHistoryInvalidError as error:
        _history_error(error)
    return Response(
        result.content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="collector_scope.csv"',
            "X-Scope-Export-ID": result.scope_export_id,
            "X-Content-SHA256": result.sha256,
        },
    )
