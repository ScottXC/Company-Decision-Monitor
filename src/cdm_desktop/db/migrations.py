from __future__ import annotations

from sqlalchemy import Engine, inspect, text

from cdm_desktop.db.models import Base


def run_migrations(engine: Engine) -> None:
    """Create missing tables and apply tiny desktop-safe schema fixes."""

    Base.metadata.create_all(engine)
    _ensure_soft_delete_columns(engine)
    _ensure_online_search_columns(engine)
    _ensure_existing_companies_are_watchlisted(engine)
    _ensure_schema_version(engine)


def _ensure_soft_delete_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required = {
        "events": ("deleted_at", "DATETIME"),
        "alerts": ("deleted_at", "DATETIME"),
    }
    with engine.begin() as conn:
        for table_name, (column_name, column_type) in required.items():
            if table_name not in tables:
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if column_name not in columns:
                conn.execute(text(f"alter table {table_name} add column {column_name} {column_type}"))


def _ensure_online_search_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required: dict[str, tuple[tuple[str, str], ...]] = {
        "companies": (
            ("source_provider", "VARCHAR(128)"),
            ("source_url", "TEXT"),
            ("source_metadata_json", "TEXT"),
        ),
        "company_universe": (
            ("source_provider", "VARCHAR(128)"),
            ("source_url", "TEXT"),
            ("raw_payload_json", "TEXT"),
        ),
    }
    with engine.begin() as conn:
        for table_name, columns in required.items():
            if table_name not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns:
                if column_name not in existing:
                    conn.execute(text(f"alter table {table_name} add column {column_name} {column_type}"))


def _ensure_existing_companies_are_watchlisted(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "companies" not in tables or "watchlist_items" not in tables:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into watchlist_items (company_id, sort_order, is_active, added_at)
                select c.id, 0, 1, CURRENT_TIMESTAMP
                from companies c
                where not exists (
                    select 1 from watchlist_items w where w.company_id = c.id
                )
                """
            )
        )


def _ensure_schema_version(engine: Engine) -> None:
    inspector = inspect(engine)
    if "app_settings" not in inspector.get_table_names():
        return

    with engine.begin() as conn:
        exists = conn.execute(
            text("select value from app_settings where key = :key"),
            {"key": "schema_version"},
        ).scalar_one_or_none()
        if exists is None:
            conn.execute(
                text("insert into app_settings (key, value, updated_at) values (:key, :value, CURRENT_TIMESTAMP)"),
                {"key": "schema_version", "value": "1"},
            )
