from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_secret_key: str = "dev-secret-change-me"
    database_url: str = "postgresql+psycopg://trophy:trophy@db:5432/trophy_case"
    local_login_enabled: bool = True
    admin_login_code: str | None = None
    admin_setup_code: str | None = None
    session_cookie_secure: bool = False
    upload_dir: str = "/uploads"
    upload_url_prefix: str = "/uploads"
    public_base_url: str | None = None
    email_from: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    admin_login_attempt_limit: int = 10
    admin_login_rate_limit_window_seconds: int = 3600
    member_login_request_limit: int = 5
    member_login_verify_limit: int = 10
    member_login_rate_limit_window_seconds: int = 3600
    google_sheet_fetch_timeout_seconds: float = 10
    google_sheet_import_max_bytes: int = 2_000_000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
