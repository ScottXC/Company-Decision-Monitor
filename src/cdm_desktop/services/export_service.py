from __future__ import annotations

import csv
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from sqlalchemy.orm import Session

from cdm_desktop.db.repositories import AlertRepository, EventRepository
from cdm_desktop.paths import AppPaths


@dataclass(frozen=True)
class ExportResult:
    path: Path
    row_count: int


class ExportService:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.paths.exports_dir.mkdir(parents=True, exist_ok=True)

    def export_events_csv(self, session: Session, path: Path | None = None, company_id: int | None = None) -> ExportResult:
        events = EventRepository(session).list(company_id=company_id, limit=10_000)
        path = path or self.paths.exports_dir / "events.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "id",
                    "company_id",
                    "document_id",
                    "event_type",
                    "event_status",
                    "title",
                    "confidence_score",
                    "materiality_score",
                    "created_at",
                ]
            )
            for event in events:
                writer.writerow(
                    [
                        event.id,
                        event.company_id,
                        event.document_id,
                        event.event_type,
                        event.event_status,
                        event.title,
                        event.confidence_score,
                        event.materiality_score,
                        event.created_at.isoformat(sep=" "),
                    ]
                )
        return ExportResult(path=path, row_count=len(events))

    def export_alerts_csv(self, session: Session, path: Path | None = None) -> ExportResult:
        alerts = AlertRepository(session).list(limit=10_000)
        path = path or self.paths.exports_dir / "alerts.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["id", "event_id", "company_id", "priority", "title", "status", "created_at"])
            for alert in alerts:
                writer.writerow(
                    [
                        alert.id,
                        alert.event_id,
                        alert.company_id,
                        alert.priority,
                        alert.title,
                        alert.status,
                        alert.created_at.isoformat(sep=" "),
                    ]
                )
        return ExportResult(path=path, row_count=len(alerts))

    def export_events_xlsx(self, session: Session, path: Path | None = None, company_id: int | None = None) -> ExportResult:
        try:
            pd = import_module("pandas")
        except ImportError as exc:
            raise RuntimeError("未安装 pandas，无法导出 Excel") from exc
        events = EventRepository(session).list(company_id=company_id, limit=10_000)
        rows = [
            {
                "id": event.id,
                "company_id": event.company_id,
                "document_id": event.document_id,
                "event_type": event.event_type,
                "event_status": event.event_status,
                "title": event.title,
                "confidence_score": event.confidence_score,
                "materiality_score": event.materiality_score,
                "created_at": event.created_at,
            }
            for event in events
        ]
        path = path or self.paths.exports_dir / "events.xlsx"
        pd.DataFrame(rows).to_excel(path, index=False)
        return ExportResult(path=path, row_count=len(rows))

    def export_alerts_xlsx(self, session: Session, path: Path | None = None) -> ExportResult:
        try:
            pd = import_module("pandas")
        except ImportError as exc:
            raise RuntimeError("未安装 pandas，无法导出 Excel") from exc
        alerts = AlertRepository(session).list(limit=10_000)
        rows = [
            {
                "id": alert.id,
                "event_id": alert.event_id,
                "company_id": alert.company_id,
                "priority": alert.priority,
                "title": alert.title,
                "status": alert.status,
                "created_at": alert.created_at,
            }
            for alert in alerts
        ]
        path = path or self.paths.exports_dir / "alerts.xlsx"
        pd.DataFrame(rows).to_excel(path, index=False)
        return ExportResult(path=path, row_count=len(rows))
