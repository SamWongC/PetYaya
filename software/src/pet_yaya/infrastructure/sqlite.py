from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from pet_yaya.domain.models import ConfirmedMemory, GrowthState, MemoryCandidate


class SQLiteDatabase:
    """Owns the database path, connection settings and schema migration."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS confirmed_memories (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pending_memories (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS growth_state (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    interaction_count INTEGER NOT NULL DEFAULT 0,
                    growth_points INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS unlocked_skills (
                    skill TEXT PRIMARY KEY
                );

                INSERT OR IGNORE INTO growth_state (
                    singleton_id, interaction_count, growth_points
                ) VALUES (1, 0, 0);
                """
            )
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, ?)",
                    ("schema_version", str(self.SCHEMA_VERSION)),
                )
            elif int(row["value"]) != self.SCHEMA_VERSION:
                raise RuntimeError(
                    "Unsupported Pet Yaya database schema version: "
                    f"{row['value']}"
                )


class SQLiteMemoryRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def list_all(self) -> tuple[ConfirmedMemory, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, category, content, source, created_at, confirmed_at
                FROM confirmed_memories
                ORDER BY confirmed_at ASC
                """
            ).fetchall()
        return tuple(
            ConfirmedMemory(
                id=row["id"],
                category=row["category"],
                content=row["content"],
                source=row["source"],
                created_at=datetime.fromisoformat(row["created_at"]),
                confirmed_at=datetime.fromisoformat(row["confirmed_at"]),
            )
            for row in rows
        )

    def save(self, memory: ConfirmedMemory) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO confirmed_memories (
                    id, category, content, source, created_at, confirmed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    category = excluded.category,
                    content = excluded.content,
                    source = excluded.source,
                    created_at = excluded.created_at,
                    confirmed_at = excluded.confirmed_at
                """,
                (
                    memory.id,
                    memory.category,
                    memory.content,
                    memory.source,
                    memory.created_at.isoformat(),
                    memory.confirmed_at.isoformat(),
                ),
            )

    def delete(self, memory_id: str) -> bool:
        with self._database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM confirmed_memories WHERE id = ?", (memory_id,)
            )
            return cursor.rowcount > 0

    def clear(self) -> None:
        with self._database.connect() as connection:
            connection.execute("DELETE FROM confirmed_memories")


class SQLitePendingMemoryRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, candidate: MemoryCandidate) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO pending_memories (
                    id, category, content, source, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    category = excluded.category,
                    content = excluded.content,
                    source = excluded.source,
                    created_at = excluded.created_at
                """,
                (
                    candidate.id,
                    candidate.category,
                    candidate.content,
                    candidate.source,
                    candidate.created_at.isoformat(),
                ),
            )

    def get(self, memory_id: str) -> MemoryCandidate | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, category, content, source, created_at
                FROM pending_memories
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()
        return self._to_candidate(row) if row is not None else None

    def remove(self, memory_id: str) -> MemoryCandidate | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, category, content, source, created_at
                FROM pending_memories
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()
            if row is not None:
                connection.execute(
                    "DELETE FROM pending_memories WHERE id = ?", (memory_id,)
                )
        return self._to_candidate(row) if row is not None else None

    def clear(self) -> None:
        with self._database.connect() as connection:
            connection.execute("DELETE FROM pending_memories")

    @staticmethod
    def _to_candidate(row: sqlite3.Row) -> MemoryCandidate:
        return MemoryCandidate(
            id=row["id"],
            category=row["category"],
            content=row["content"],
            source=row["source"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class SQLiteGrowthRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get(self) -> GrowthState:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT interaction_count, growth_points
                FROM growth_state
                WHERE singleton_id = 1
                """
            ).fetchone()
            skills = connection.execute(
                "SELECT skill FROM unlocked_skills ORDER BY skill"
            ).fetchall()
        if row is None:
            return GrowthState()
        return GrowthState(
            interaction_count=row["interaction_count"],
            growth_points=row["growth_points"],
            unlocked_skills=[item["skill"] for item in skills],
        )

    def save(self, state: GrowthState) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO growth_state (
                    singleton_id, interaction_count, growth_points
                ) VALUES (1, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    interaction_count = excluded.interaction_count,
                    growth_points = excluded.growth_points
                """,
                (state.interaction_count, state.growth_points),
            )
            connection.execute("DELETE FROM unlocked_skills")
            connection.executemany(
                "INSERT INTO unlocked_skills (skill) VALUES (?)",
                ((skill,) for skill in dict.fromkeys(state.unlocked_skills)),
            )

    def reset(self) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE growth_state
                SET interaction_count = 0, growth_points = 0
                WHERE singleton_id = 1
                """
            )
            connection.execute("DELETE FROM unlocked_skills")

