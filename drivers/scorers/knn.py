"""
k 近鄰評分：分別找出正常組、碰撞組裡最接近的 k 個範例，比較平均距離。
不需要訓練，新增範例後立即生效。
"""
from __future__ import annotations

from typing import Any

import numpy as np

from core.interfaces import ScorerDriver
from core.types import ScoreResult
from drivers.scorers.common import check_bank, cosine_distance, distance_ratio_score, normalize


class KNNScorer(ScorerDriver):
    def __init__(self, k: int = 3):
        if k < 1:
            raise ValueError("k must be >= 1")
        self.k = int(k)
        self._bank: dict[str, tuple[list[str], np.ndarray]] = {}
        self._positive = ""
        self._negative = ""

    def fit(self, bank, positive, negative) -> None:
        check_bank(bank, positive, negative)
        self._bank = {label: (list(ids), normalize(matrix)) for label, (ids, matrix) in bank.items()}
        self._positive, self._negative = positive, negative

    def _nearest(self, label: str, embedding: np.ndarray) -> tuple[float, str, float]:
        ids, matrix = self._bank[label]
        distances = cosine_distance(matrix, embedding)
        k = min(self.k, len(ids))
        order = np.argsort(distances)[:k]
        return float(distances[order].mean()), ids[order[0]], float(distances[order[0]])

    def score(self, embedding: np.ndarray) -> ScoreResult:
        if not self._bank:
            return ScoreResult.not_ready("scorer 尚未建立（範例不足）")
        d_pos, pos_id, pos_min = self._nearest(self._positive, embedding)
        d_neg, neg_id, neg_min = self._nearest(self._negative, embedding)
        if pos_min <= neg_min:
            nearest = {"exemplar_id": pos_id, "label": self._positive, "distance": pos_min}
        else:
            nearest = {"exemplar_id": neg_id, "label": self._negative, "distance": neg_min}
        return ScoreResult(
            score=distance_ratio_score(d_pos, d_neg),
            ready=True,
            nearest=nearest,
            details={f"distance_{self._positive}": d_pos, f"distance_{self._negative}": d_neg},
        )

    def info(self) -> dict[str, Any]:
        return {"k": self.k, "counts": {label: len(ids) for label, (ids, _) in self._bank.items()}}
