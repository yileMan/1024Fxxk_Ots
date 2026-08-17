from fastapi import FastAPI


def create_app() -> FastAPI:
    application = FastAPI(title="OTS Backend")

    @application.get("/")
    async def root() -> dict[str, str]:
        return {"message": "OTS backend is running"}

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
