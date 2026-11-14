"""
分數 → 風險等級。

只處理數字，不知道分數是哪個模型算出來的。
等級門檻與顏色由 config.RISK 設定。
"""
from __future__ import annotations

from collections import deque
from typing import Any

NOT_READY_LEVEL = {"name": "NOT READY", "color": "#8a8f98"}


class RiskLeveler:
    def __init__(self, levels: list[dict[str, Any]], smoothing_window: int = 1):
        if not levels:
            raise ValueError("levels must not be empty")
        if smoothing_window < 1:
            raise ValueError("smoothing_window must be >= 1")
        self.levels = sorted(levels, key=lambda level: level["min"])
        self._window: deque[float] = deque(maxlen=smoothing_window)

    def reset(self) -> None:
        self._window.clear()

    def classify(self, score: float | None) -> dict[str, Any]:
        if score is None:
            return NOT_READY_LEVEL
        chosen = self.levels[0]
        for level in self.levels:
            if score >= level["min"]:
                chosen = level
        return chosen

    def update(self, raw_score: float | None) -> tuple[float | None, dict[str, Any]]:
        """加入一個新分數，回傳 (平滑後分數, 等級)。"""
        if raw_score is None:
            self.reset()
            return None, NOT_READY_LEVEL
        self._window.append(float(raw_score))
        smoothed = sum(self._window) / len(self._window)
        return smoothed, self.classify(smoothed)
