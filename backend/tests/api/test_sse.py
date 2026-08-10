from __future__ import annotations

from se_mentor.events.bus import EventBus


def test_T090_sse_reconnects_without_missing_persisted_events() -> None:
    bus = EventBus()
    first = bus.publish(task_id="task-1", event_type="status", payload={"state": "STARTED"})
    second = bus.publish(task_id="task-1", event_type="status", payload={"state": "VALIDATING"})
    third = bus.publish(task_id="task-1", event_type="status", payload={"state": "COMPLETED"})

    replay = bus.replay(task_id="task-1", last_event_id=first.event_id)

    assert [event.event_id for event in replay] == [second.event_id, third.event_id]
    assert first.event_id < second.event_id < third.event_id
