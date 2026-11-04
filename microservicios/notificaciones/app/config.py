"""Environment-driven configuration with local-friendly defaults."""

import os
from dataclasses import dataclass, field


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class Settings:
    # HTTP
    port: int = field(default_factory=lambda: int(_env("PORT", "8084")))

    # Database (defaults target a local Postgres 16)
    db_host: str = field(default_factory=lambda: _env("DB_HOST", "localhost"))
    db_port: int = field(default_factory=lambda: int(_env("DB_PORT", "5432")))
    db_name: str = field(default_factory=lambda: _env("DB_NAME", "notificaciones"))
    db_user: str = field(default_factory=lambda: _env("DB_USER", "postgres"))
    db_password: str = field(default_factory=lambda: _env("DB_PASSWORD", "postgres"))

    # RabbitMQ (defaults match a local `rabbitmq:3-management` container with guest/guest)
    rabbitmq_host: str = field(default_factory=lambda: _env("RABBITMQ_HOST", "localhost"))
    rabbitmq_port: int = field(default_factory=lambda: int(_env("RABBITMQ_PORT", "5672")))
    rabbitmq_user: str = field(default_factory=lambda: _env("RABBITMQ_USER", "guest"))
    rabbitmq_password: str = field(default_factory=lambda: _env("RABBITMQ_PASSWORD", "guest"))

    # Background AMQP consumer can be disabled for tests / read-only runs
    consumer_enabled: bool = field(
        default_factory=lambda: _env("CONSUMER_ENABLED", "true").lower() in ("1", "true", "yes")
    )

    # Optional full-URL override (used by the test suite with SQLite)
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", ""))

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
