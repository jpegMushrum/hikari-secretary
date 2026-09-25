from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


LATEST_VERSION = 2


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")}


def migration_001_baseline(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            entities_json TEXT NOT NULL DEFAULT '[]',
            rich_message_json TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            scheduled_at TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            notified INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            path TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            platform TEXT NOT NULL,
            target_key TEXT NOT NULL,
            target_name TEXT NOT NULL,
            destination TEXT NOT NULL,
            message_thread_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT,
            external_id TEXT,
            last_error TEXT,
            published_at TEXT,
            UNIQUE(post_id, target_key)
        );
        CREATE INDEX IF NOT EXISTS idx_delivery_due
        ON deliveries(status, next_attempt_at);
        CREATE TABLE IF NOT EXISTS events (
            post_id INTEGER PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            cancelled_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            surname TEXT NOT NULL,
            given_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS registration_flows (
            user_id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            stage TEXT NOT NULL,
            surname TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS profile_edit_flows (
            user_id INTEGER PRIMARY KEY,
            stage TEXT NOT NULL,
            surname TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES user_profiles(user_id),
            reminders_enabled INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'registered',
            registered_at TEXT NOT NULL,
            cancelled_at TEXT,
            reminder_sent_at TEXT,
            attendance_prompt_sent_at TEXT,
            attended INTEGER,
            attendance_recorded_at TEXT,
            UNIQUE(post_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_registrations_user
        ON registrations(user_id, status);
        """
    )

    compatibility_columns = {
        "deliveries": [("message_thread_id", "INTEGER")],
        "posts": [("rich_message_json", "TEXT")],
        "events": [
            ("status", "TEXT NOT NULL DEFAULT 'active'"),
            ("cancelled_at", "TEXT"),
        ],
    }
    for table, additions in compatibility_columns.items():
        existing = _columns(db, table)
        for name, definition in additions:
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def migration_002_profile_v2(db: sqlite3.Connection) -> None:
    existing = _columns(db, "user_profiles")
    additions = (
        ("full_name", "TEXT"),
        ("telegram_username", "TEXT"),
        ("telegram_first_name", "TEXT"),
        ("telegram_last_name", "TEXT"),
    )
    for name, definition in additions:
        if name not in existing:
            db.execute(f"ALTER TABLE user_profiles ADD COLUMN {name} {definition}")

    db.execute(
        """UPDATE user_profiles
           SET full_name=TRIM(COALESCE(given_name, '') || ' ' || COALESCE(surname, ''))
           WHERE full_name IS NULL OR TRIM(full_name)=''"""
    )
    missing = db.execute(
        "SELECT COUNT(*) FROM user_profiles WHERE full_name IS NULL OR TRIM(full_name)=''"
    ).fetchone()[0]
    if missing:
        raise RuntimeError(f"Не удалось сформировать full_name для {missing} профилей")

    # These rows contain only unfinished dialog state, not completed registrations.
    db.execute("DELETE FROM registration_flows")
    db.execute("DELETE FROM profile_edit_flows")


MIGRATIONS: tuple[tuple[int, str, Callable[[sqlite3.Connection], None]], ...] = (
    (1, "baseline", migration_001_baseline),
    (2, "profile_v2", migration_002_profile_v2),
)


def migrate(path: Path, create_backup: bool = True) -> list[int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists() and path.stat().st_size > 0
    db = sqlite3.connect(path)
    applied_now: list[int] = []
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version INTEGER PRIMARY KEY,
                   name TEXT NOT NULL,
                   applied_at TEXT NOT NULL
               )"""
        )
        db.commit()
        applied = {row[0] for row in db.execute("SELECT version FROM schema_migrations")}
        pending = [item for item in MIGRATIONS if item[0] not in applied]
        if pending and existed and create_backup:
            backup_dir = path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = backup_dir / f"{path.stem}-before-v{pending[0][0]}-{stamp}{path.suffix}"
            backup = sqlite3.connect(backup_path)
            try:
                db.backup(backup)
            finally:
                backup.close()
            print(f"Backup created: {backup_path}", flush=True)

        for version, name, operation in pending:
            print(f"Applying migration {version}: {name}", flush=True)
            try:
                db.execute("BEGIN IMMEDIATE")
                operation(db)
                db.execute(
                    "INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,?)",
                    (version, name, datetime.now(timezone.utc).isoformat()),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            applied_now.append(version)
        return applied_now
    finally:
        db.close()


def main() -> None:
    path = Path(os.getenv("DATABASE_PATH", "/app/data/bot.sqlite3"))
    applied = migrate(path)
    if applied:
        print(f"Migrations complete. Current version: {max(applied)}", flush=True)
    else:
        print(f"Database is up to date. Current version: {LATEST_VERSION}", flush=True)


if __name__ == "__main__":
    main()
