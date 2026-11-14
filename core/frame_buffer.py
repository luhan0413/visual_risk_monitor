"""執行緒安全的影格環狀緩衝區。"""
from __future__ import annotations

import threading
from collections import deque

from core.types import Frame


class FrameBuffer:
    def __init__(self, maxlen: int):
        if maxlen < 1:
            raise ValueError("maxlen must be >= 1")
        self._frames: deque[Frame] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, frame: Frame) -> None:
        with self._lock:
            self._frames.append(frame)

    def latest(self) -> Frame | None:
        with self._lock:
            return self._frames[-1] if self._frames else None

    def clip(self, length: int) -> list[Frame]:
        """回傳最近 length 張（不足時回傳目前全部）。"""
        with self._lock:
            if length <= 0:
                return []
            return list(self._frames)[-length:]

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)
