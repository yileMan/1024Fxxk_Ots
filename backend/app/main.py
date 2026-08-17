import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.health import router as health_router
from app.infrastructure.database import Database
from app.infrastructure.settings import Settings

logger = logging.getLogger("ots")


def create_app() -> FastAPI:
    settings = Settings.from_environment()
    application = FastAPI(title="OTS Backend", version="0.1.0")
    application.state.database = Database(settings.database_url)

    @application.middleware("http")
    async def correlation_id(request: Request, call_next):
        request_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = request_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request_id
        logger.info("request_completed correlation_id=%s status=%s", request_id, response.status_code)
        return response

    def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "code": code,
                "message": message,
                "correlation_id": getattr(request.state, "correlation_id", "generated-by-middleware"),
            },
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return error_response(request, exc.status_code, code, "请求的资源不可用")

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "VALIDATION_ERROR", "请求不符合接口契约")

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("request_failed")
        return error_response(request, 500, "INTERNAL_ERROR", "服务暂时不可用")

    @application.get("/")
    async def root() -> dict[str, str]:
        return {"message": "OTS backend is running"}

    application.include_router(health_router, prefix="/api/v1")

    return application


app = create_app()
