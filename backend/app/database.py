from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float
from sqlalchemy.orm import declarative_base, sessionmaker, Session


Base = declarative_base()


class AuditLog(Base):
    """SQLAlchemy model for audit log entries."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    action_type = Column(String(50), nullable=False, index=True)
    target_type = Column(String(50), nullable=False, index=True)
    target_name = Column(String(255), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    output = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    duration_ms = Column(Float, nullable=True)

    def set_metadata(self, data: dict[str, Any]) -> None:
        self.metadata_json = json.dumps(data) if data else None

    def get_metadata(self) -> dict[str, Any]:
        if not self.metadata_json:
            return {}
        return json.loads(self.metadata_json)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "action_type": self.action_type,
            "target_type": self.target_type,
            "target_name": self.target_name,
            "status": self.status,
            "output": self.output,
            "error_message": self.error_message,
            "metadata": self.get_metadata(),
            "duration_ms": self.duration_ms,
        }


class Database:
    """Database connection manager."""

    def __init__(self, db_path: str = "siteflow.db"):
        self.db_path = db_path
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def init_db(self) -> None:
        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()


_database: Database | None = None


def get_database(db_path: str = "siteflow.db") -> Database:
    global _database
    if _database is None:
        _database = Database(db_path)
    return _database


def init_database(db_path: str = "siteflow.db") -> Database:
    db = get_database(db_path)
    db.init_db()
    return db
