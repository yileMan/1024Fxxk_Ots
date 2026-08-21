import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.health import router as health_router
from app.api.routes.authentication import router as authentication_router
from app.api.routes.users import router as users_router
from app.api.routes.products import router as products_router
from app.api.routes.ots import router as ots_router
from app.infrastructure.database import Database
from app.infrastructure.settings import Settings
from app.services.authentication import AuthenticationService
from app.services.users import UserManagementService
from app.services.products import ProductManagementService
from app.services.ots import OtsManagementService

logger = logging.getLogger("ots")


def create_app() -> FastAPI:
    settings = Settings.from_environment()
    application = FastAPI(title="OTS Backend", version="0.1.0")
    application.state.settings = settings
    application.state.database = Database(settings.database_url)
    if application.state.database.session_factory is not None:
        application.state.authentication_service = AuthenticationService(
            application.state.database.session_factory,
        )
        application.state.user_management_service = UserManagementService(
            application.state.database.session_factory,
            application.state.authentication_service,
        )
        application.state.product_management_service = ProductManagementService(
            application.state.database.session_factory,
        )
        application.state.ots_management_service = OtsManagementService(
            application.state.database.session_factory,
        )

    @application.middleware("http")
    async def correlation_id(request: Request, call_next):
        request_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = request_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request_id
        logger.info("request_completed correlation_id=%s status=%s", request_id, response.status_code)
        return response

    def error_response(request: Request, status: int, code: str, message: str, extra: dict[str, object] | None = None) -> JSONResponse:
        content: dict[str, object] = {
            "code": code,
            "message": message,
            "correlation_id": getattr(request.state, "correlation_id", "generated-by-middleware"),
        }
        if extra:
            content.update(extra)
        return JSONResponse(
            status_code=status,
            content=content,
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            return error_response(
                request,
                exc.status_code,
                str(exc.detail.get("code", "HTTP_ERROR")),
                str(exc.detail.get("message", "请求的资源不可用")),
                {key: value for key, value in exc.detail.items() if key not in {"code", "message"}},
            )
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
    application.include_router(authentication_router, prefix="/api/v1")
    application.include_router(users_router, prefix="/api/v1")
    application.include_router(products_router, prefix="/api/v1")
    application.include_router(ots_router, prefix="/api/v1")

    return application


app = create_app()
