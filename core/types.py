"""
共用資料型別。

所有層（driver / service / route）之間只用這裡定義的型別交換資料，
所以更換相機、模型或評分方法時，上層程式不需要改動。

影像慣例：一律為 RGB、uint8、形狀 (H, W, 3) 的 numpy.ndarray。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Frame:
    """來源取得的一張影格。"""

    image: np.ndarray  # RGB uint8 (H, W, 3)
    timestamp: float  # time.time()
    index: int  # 從來源開始後的流水號


@dataclass
class ScoreResult:
    """
    Scorer 的輸出。

    score: 0～100，代表「像 positive 類別（例如 collision）的程度」。
           範例庫不足等情況下為 None。
    """

    score: float | None
    ready: bool
    reason: str | None = None
    nearest: dict[str, Any] | None = None  # {"exemplar_id", "label", "distance"}
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def not_ready(cls, reason: str) -> "ScoreResult":
        return cls(score=None, ready=False, reason=reason)


@dataclass
class RiskAssessment:
    """一次分析的完整結果，也是推送到前端的資料。"""

    timestamp: float
    raw_score: float | None
    score: float | None  # 平滑後
    level: str
    color: str
    ready: bool
    reason: str | None
    nearest: dict[str, Any] | None
    latency_ms: float | None
    encoder: str | None
    scorer: str | None
    frame_index: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
