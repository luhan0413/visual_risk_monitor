"""
評分服務：管理目前使用的 ScorerDriver。

範例庫或模型有變動時，下一次評分前會自動重新建立（必要時重算範例特徵）。
"""
from __future__ import annotations

import threading
from typing import Any, Callable

import numpy as np

from core.interfaces import ScorerDriver
from core.types import ScoreResult
from drivers import loader
from services.encoder_service import EncoderService
from services.exemplar_service import ExemplarService


class ScoringService:
    def __init__(
        self,
        exemplars: ExemplarService,
        encoders: EncoderService,
        positive: str,
        negative: str,
        min_per_label: int,
        factory: Callable[[str], ScorerDriver] = loader.create_scorer,
    ):
        self.exemplars = exemplars
        self.encoders = encoders
        self.positive = positive
        self.negative = negative
        self.min_per_label = int(min_per_label)
        self._factory = factory
        self._lock = threading.RLock()
        self._driver: ScorerDriver | None = None
        self._name: str | None = None
        self._fit_key: tuple | None = None
        self._ready = False
        self._reason: str | None = "尚未建立"

    @property
    def name(self) -> str | None:
        return self._name

    def select(self, name: str) -> dict[str, Any]:
        driver = self._factory(name)
        with self._lock:
            self._driver, self._name = driver, name
            self._fit_key, self._ready, self._reason = None, False, "尚未建立"
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self._name,
                "ready": self._ready,
                "reason": self._reason,
                "counts": self.exemplars.counts(),
                "min_per_label": self.min_per_label,
                "positive": self.positive,
                "negative": self.negative,
                "info": self._driver.info() if self._driver and self._ready else {},
            }

    def refresh(self) -> bool:
        """需要時重新 fit。回傳是否可以評分。"""
        with self._lock:
            if self._driver is None:
                self._ready, self._reason = False, "尚未選擇 scorer"
                return False
            if not self.encoders.ready:
                self._ready, self._reason = False, "encoder 尚未就緒"
                return False
            key = (self.encoders.name, self.encoders.generation, self.exemplars.version, self._name)
            if key == self._fit_key:
                return self._ready
            counts = self.exemplars.counts()
            missing = [f"{label} {counts[label]}/{self.min_per_label}"
                       for label in (self.negative, self.positive) if counts[label] < self.min_per_label]
            if missing:
                self._fit_key, self._ready = key, False
                self._reason = "範例不足：" + "、".join(missing)
                return False
            try:
                bank = self.exemplars.build_bank(self.encoders.name, self.encoders.encode)
                self._driver.fit(bank, positive=self.positive, negative=self.negative)
            except Exception as exc:  # noqa: BLE001
                self._fit_key, self._ready, self._reason = None, False, f"建立失敗：{exc}"
                return False
            self._fit_key, self._ready, self._reason = key, True, None
            return True

    def score(self, embedding: np.ndarray) -> ScoreResult:
        if not self.refresh():
            return ScoreResult.not_ready(self._reason or "scorer 尚未就緒")
        with self._lock:
            return self._driver.score(embedding)
