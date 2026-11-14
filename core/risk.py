"""
分數 → 風險等級。

只處理數字，不知道分數是哪個模型算出來的。
等級門檻與顏色由 config.RISK 設定。
"""
from __future__ import annotations

from collections import deque
from typing import Any

NOT_READY_NAME = "NOT READY"
NOT_READY_LEVEL = {"name": NOT_READY_NAME, "color": "#8a8f98"}  # 預設值


class RiskLeveler:
    def __init__(self, levels: list[dict[str, Any]], smoothing_window: int = 1, not_ready_color: str | None = None):
        if not levels:
            raise ValueError("levels must not be empty")
        if smoothing_window < 1:
            raise ValueError("smoothing_window must be >= 1")
        self.levels = sorted(levels, key=lambda level: level["min"])
        self._window: deque[float] = deque(maxlen=smoothing_window)
        self.not_ready = (
            {"name": NOT_READY_NAME, "color": not_ready_color} if not_ready_color else NOT_READY_LEVEL
        )

    def reset(self) -> None:
        self._window.clear()

    def classify(self, score: float | None) -> dict[str, Any]:
        if score is None:
            return self.not_ready
        chosen = self.levels[0]
        for level in self.levels:
            if score >= level["min"]:
                chosen = level
        return chosen

    def update(self, raw_score: float | None) -> tuple[float | None, dict[str, Any]]:
        """加入一個新分數，回傳 (平滑後分數, 等級)。"""
        if raw_score is None:
            self.reset()
            return None, self.not_ready
        self._window.append(float(raw_score))
        smoothed = sum(self._window) / len(self._window)
        return smoothed, self.classify(smoothed)
