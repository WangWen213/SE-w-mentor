import { useCallback, useEffect, useRef, useState } from "react";

import type { MentorApi, TaskEvent } from "../api/mentorApi";

const reconnectHeader = "Last-Event-ID";

export function useTaskEvents(api: MentorApi, taskId: string | null) {
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [reconnecting, setReconnecting] = useState(false);
  const lastEventId = useRef<number | null>(null);
  const seenEventIds = useRef<Set<number>>(new Set());
  const activeTaskId = useRef<string | null>(taskId);

  const reconnect = useCallback(async () => {
    if (!taskId) {
      return;
    }
    activeTaskId.current = taskId;
    setReconnecting(true);
    try {
      void reconnectHeader;
      const nextEvents = await api.getTaskEvents(taskId, lastEventId.current);
      if (activeTaskId.current !== taskId) {
        return;
      }
      setEvents((current) => {
        const merged = [...current];
        for (const event of nextEvents) {
          if (event.taskId !== taskId || seenEventIds.current.has(event.eventId)) {
            continue;
          }
          seenEventIds.current.add(event.eventId);
          lastEventId.current = Math.max(lastEventId.current ?? 0, event.eventId);
          merged.push(event);
        }
        return merged;
      });
    } finally {
      if (activeTaskId.current === taskId) {
        setReconnecting(false);
      }
    }
  }, [api, taskId]);

  useEffect(() => {
    activeTaskId.current = taskId;
    setEvents([]);
    lastEventId.current = null;
    seenEventIds.current = new Set();
    void reconnect();
    return () => {
      activeTaskId.current = null;
    };
  }, [reconnect, taskId]);

  return { events, lastEventId: lastEventId.current, reconnect, reconnecting };
}
