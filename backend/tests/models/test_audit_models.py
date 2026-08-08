from __future__ import annotations

from pathlib import Path

import pytest
from phase1_test_helpers import create_schema, execute, row_count, seed_task_graph
from sqlalchemy import exc

from se_mentor.contracts.enums import EventType
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.audit import (
    AlertEvent,
    AlertSeverity,
    AlertStatus,
    AuditActorType,
    AuditEvent,
)


def test_T018_audit_update_delete_is_rejected_and_alert_requires_task_or_system_scope(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "audit.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        event = AuditEvent(
            task_id=ids["task_id"],
            correlation_id="corr-1",
            actor_type=AuditActorType.SYSTEM,
            actor_id="codex",
            event_type=EventType.TASK_CREATED,
            payload_summary="Task created.",
            evidence_json='[{"source":"T018","summary":"audit"}]',
        )
        session.add(event)
        session.flush()
        event_id = event.id

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            "UPDATE audit_events SET payload_summary = 'changed' WHERE id = :event_id",
            {"event_id": event_id},
        )
    with pytest.raises(exc.IntegrityError):
        execute(engine, "DELETE FROM audit_events WHERE id = :event_id", {"event_id": event_id})
    assert row_count(engine, "audit_events") == 1

    with pytest.raises(exc.IntegrityError):
        execute(
            engine,
            """
            INSERT INTO alert_events (
                id, task_id, system_scope, severity, status, summary, evidence_json,
                created_at, updated_at
            )
            VALUES (
                'orphan-alert', NULL, 0, 'HIGH', 'OPEN', 'orphan', '[]',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """,
            {},
        )


def test_T018_alert_status_and_retention_doc(tmp_path: Path) -> None:
    engine = create_schema(tmp_path / "alert.sqlite3")
    ids = seed_task_graph(engine, tmp_path)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        session.add(
            AlertEvent(
                task_id=ids["task_id"],
                system_scope=False,
                severity=AlertSeverity.HIGH,
                status=AlertStatus.OPEN,
                summary="Governance warning.",
                evidence_json='[{"source":"T018","summary":"alert"}]',
            )
        )
        session.add(
            AlertEvent(
                system_scope=True,
                severity=AlertSeverity.INFO,
                status=AlertStatus.RESOLVED,
                summary="System retention note.",
                evidence_json='[{"source":"T018","summary":"system"}]',
            )
        )
        session.flush()

    retention_text = (Path(__file__).resolve().parents[3] / "docs" / "DATA_RETENTION.md").read_text(
        encoding="utf-8"
    )
    assert "audit_events" in retention_text
    assert "governance_decisions" in retention_text
    assert "artifact" in retention_text.lower()
