from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.repositories import SettingsRepository
from cdm_desktop.paths import AppPaths
from cdm_desktop.services.ingestion_service import IngestionService


class SchedulerService:
    def __init__(self, db: DatabaseManager, paths: AppPaths) -> None:
        self.db = db
        self.paths = paths
        self.scheduler = BackgroundScheduler()
        self.ingestion = IngestionService(db, paths)

    def start_from_settings(self) -> None:
        with self.db.session() as session:
            settings = SettingsRepository(session)
            enabled = settings.get("monitoring_enabled", "false") == "true"
            interval = int(settings.get("monitoring_interval_minutes", "60") or "60")
        if enabled:
            self.enable(interval)

    def enable(self, interval_minutes: int) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        self.scheduler.add_job(
            self.ingestion.run_all_enabled_sources,
            "interval",
            minutes=max(1, interval_minutes),
            id="run_all_enabled_sources",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def disable(self) -> None:
        if self.scheduler.running:
            self.scheduler.remove_all_jobs()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def reset_runtime(self) -> None:
        self.shutdown()
        self.scheduler = BackgroundScheduler()
        self.ingestion = IngestionService(self.db, self.paths)
