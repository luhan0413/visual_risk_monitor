"""中心點評分：比較與正常組、碰撞組「平均特徵」的距離。對個別離群範例比較不敏感。"""
from __future__ import annotations

from typing import Any

import numpy as np

from core.interfaces import ScorerDriver
from core.types import ScoreResult
from drivers.scorers.common import check_bank, check_sharpness, cosine_distance, distance_ratio_score, normalize


class CentroidScorer(ScorerDriver):
    def __init__(self, sharpness: float = 1.0):
        self.sharpness = check_sharpness(sharpness)
        self._bank: dict[str, tuple[list[str], np.ndarray]] = {}
        self._centroids: dict[str, np.ndarray] = {}
        self._positive = ""
        self._negative = ""

    def fit(self, bank, positive, negative) -> None:
        check_bank(bank, positive, negative)
        self._bank = {label: (list(ids), normalize(matrix)) for label, (ids, matrix) in bank.items()}
        self._centroids = {label: normalize(matrix.mean(axis=0)) for label, (_, matrix) in self._bank.items()}
        self._positive, self._negative = positive, negative

    def score(self, embedding: np.ndarray) -> ScoreResult:
        if not self._centroids:
            return ScoreResult.not_ready("scorer 尚未建立（範例不足）")
        d_pos = float(cosine_distance(self._centroids[self._positive][None], embedding)[0])
        d_neg = float(cosine_distance(self._centroids[self._negative][None], embedding)[0])

        # 仍回報最接近的單一範例，讓介面可以顯示縮圖
        best = None
        for label in (self._positive, self._negative):
            ids, matrix = self._bank[label]
            distances = cosine_distance(matrix, embedding)
            index = int(np.argmin(distances))
            if best is None or distances[index] < best["distance"]:
                best = {"exemplar_id": ids[index], "label": label, "distance": float(distances[index])}

        return ScoreResult(
            score=distance_ratio_score(d_pos, d_neg, self.sharpness),
            ready=True,
            nearest=best,
            details={f"distance_{self._positive}": d_pos, f"distance_{self._negative}": d_neg},
        )

    def info(self) -> dict[str, Any]:
        return {"sharpness": self.sharpness, "counts": {label: len(ids) for label, (ids, _) in self._bank.items()}}
