"""簡單的 publish / subscribe，用來把分析結果推送給前端（SSE）。"""
from __future__ import annotations

import queue
import threading
from typing import Any


class EventBus:
    def __init__(self, queue_size: int = 100):
        self._queue_size = queue_size
        self._subscribers: set[queue.Queue] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=self._queue_size)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event: str, data: Any) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait((event, data))
            except queue.Full:
                # 前端太慢時丟掉最舊的一筆，避免卡住分析迴圈
                try:
                    q.get_nowait()
                    q.put_nowait((event, data))
                except (queue.Empty, queue.Full):
                    pass
