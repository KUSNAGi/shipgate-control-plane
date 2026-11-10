from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHIPGATE_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./shipgate.db"
    environment: str = "development"
    log_level: str = "INFO"
    max_request_bytes: int = Field(default=32_768, ge=1024, le=1_048_576)
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        if value not in {"development", "test", "production"}:
            raise ValueError("environment must be development, test or production")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database(cls, value: str) -> str:
        if not value.startswith(("sqlite://", "postgresql+psycopg://")):
            raise ValueError("database_url must use SQLite or PostgreSQL with psycopg")
        return value

    def validate_for_serving(self) -> None:
        if self.environment == "production" and not self.database_url.startswith(
            "postgresql+psycopg://"
        ):
            raise ValueError("production requires PostgreSQL")
        if self.environment == "production" and any(
            h in {"*", "localhost", "127.0.0.1", "testserver"} for h in self.trusted_hosts
        ):
            raise ValueError("production requires explicit external trusted hosts")


def get_settings() -> Settings:
    settings = Settings()
    settings.validate_for_serving()
    return settings
