from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth import member_id_from_request
from app.core.config import settings
from app.db.models import Member
from app.db.session import SessionLocal
from app.routers import admin, auth, competitions, leaderboard, members, results, styles, submissions
from app.services.csrf import csrf_token_for_request, require_csrf, set_csrf_cookie


def create_app() -> FastAPI:
    app = FastAPI(title="Trophy Case", dependencies=[Depends(require_csrf)])
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.upload_url_prefix,
        StaticFiles(directory=settings.upload_dir),
        name="uploads",
    )

    @app.middleware("http")
    async def load_current_member(request, call_next):
        csrf_token = csrf_token_for_request(request)
        request.state.csrf_token = csrf_token
        request.state.current_member = None
        member_id = member_id_from_request(request)
        if member_id is None:
            response = await call_next(request)
            add_upload_response_headers(request, response)
            set_csrf_cookie(response, csrf_token)
            return response

        with SessionLocal() as db:
            member = db.get(Member, member_id)
            if member is not None and member.deactivated_at is None:
                request.state.current_member = member
            response = await call_next(request)
            add_upload_response_headers(request, response)
            set_csrf_cookie(response, csrf_token)
            return response

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(submissions.router)
    app.include_router(results.router)
    app.include_router(competitions.router)
    app.include_router(styles.router)
    app.include_router(members.router)
    app.include_router(leaderboard.router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database unavailable.") from exc
        return {"status": "ok"}

    return app


def add_upload_response_headers(request, response) -> None:
    upload_prefix = settings.upload_url_prefix.rstrip("/")
    if not request.url.path.startswith(f"{upload_prefix}/"):
        return
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    if Path(request.url.path).suffix.lower() not in {".gif", ".jpeg", ".jpg", ".png", ".webp"}:
        response.headers.setdefault("Content-Disposition", "attachment")


app = create_app()
