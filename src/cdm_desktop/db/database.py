from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from cdm_desktop.db.migrations import run_migrations
from cdm_desktop.paths import AppPaths, get_app_paths


class DatabaseManager:
    def __init__(self, db_path: str | Path | None = None, paths: AppPaths | None = None) -> None:
        self.paths = paths or get_app_paths()
        self.db_path = Path(db_path) if db_path is not None else self.paths.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(
            f"sqlite:///{self.db_path}",
            future=True,
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        run_migrations(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
