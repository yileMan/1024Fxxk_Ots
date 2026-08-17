from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["platform"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    if request.app.state.database.check():
        return JSONResponse({"service": "available", "database": "available"})
    return JSONResponse(
        status_code=503,
        content={
            "code": "DATABASE_UNAVAILABLE",
            "message": "数据库不可用",
            "correlation_id": getattr(request.state, "correlation_id", "generated-by-middleware"),
        },
    )
