from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mogul.api.routes import analysis, deals, markets, portfolio
from mogul.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Realtor Mogul API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(analysis.router)
    app.include_router(deals.router)
    app.include_router(markets.router)
    app.include_router(portfolio.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
