"""
Driver 介面（系統的「插座規格」）。

新增相機、模型或評分方法時，只要寫一個繼承這裡基底類別的 driver，
再到 drivers/loader.py 登記、config.py 設定即可，services 以上都不用改。

    SourceDriver   影像來源：brain-device 相機、USB 相機、錄影回放 …
    EncoderDriver  特徵模型：V-JEPA 2、之後的其他模型 …
    ScorerDriver   評分方法：kNN、centroid、之後的分類器 …
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from core.types import ScoreResult


class SourceDriver(ABC):
    """影像來源。read() 由 source_service 的擷取執行緒反覆呼叫。"""

    @abstractmethod
    def open(self) -> None:
        """開始連線 / 開檔。失敗時 raise。"""

    @abstractmethod
    def close(self) -> None:
        """釋放資源。重複呼叫必須安全。"""

    @abstractmethod
    def read(self) -> np.ndarray | None:
        """回傳最新一張 RGB 影像；暫時取不到時回傳 None。"""

    def status(self) -> dict[str, Any]:
        return {}

    def options(self) -> dict[str, Any]:
        """可供前端選擇的選項，例如回放可選的影片清單。"""
        return {}

    def configure(self, **kwargs: Any) -> None:
        """open() 之前套用前端選擇的選項（例如選哪支影片）。"""
        if kwargs:
            raise ValueError(f"此來源不支援選項：{', '.join(kwargs)}")


class EncoderDriver(ABC):
    """把一段影格轉成一個特徵向量。"""

    @abstractmethod
    def load(self) -> None:
        """載入模型權重（可能很慢，由 encoder_service 在背景執行）。"""

    @abstractmethod
    def unload(self) -> None:
        """釋放模型與 GPU 記憶體。"""

    @abstractmethod
    def encode(self, frames: list[np.ndarray]) -> np.ndarray:
        """
        frames: 依時間排序的 RGB 影像，長度 >= 1。
        回傳: 1 維 float32 特徵向量。
        """

    def info(self) -> dict[str, Any]:
        return {}


class ScorerDriver(ABC):
    """依範例庫，把特徵向量轉成 0～100 的分數。"""

    @abstractmethod
    def fit(
        self,
        bank: dict[str, tuple[list[str], np.ndarray]],
        positive: str,
        negative: str,
    ) -> None:
        """
        bank: {label: (exemplar_ids, embeddings[N, D])}
        positive: 分數越高代表越像的類別（例如 "collision"）
        negative: 對照類別（例如 "normal"）
        """

    @abstractmethod
    def score(self, embedding: np.ndarray) -> ScoreResult:
        """回傳 ScoreResult；尚未 fit 時回傳 ScoreResult.not_ready(...)。"""

    def info(self) -> dict[str, Any]:
        return {}
