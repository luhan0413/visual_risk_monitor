"""Scorer 共用工具。"""
from __future__ import annotations

import numpy as np


def normalize(vectors: np.ndarray) -> np.ndarray:
    """L2 正規化（支援 1 維或 2 維）。"""
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.maximum(norms, 1e-8)


def cosine_distance(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """matrix 每一列與 vector 的 cosine distance（0 = 完全相同，2 = 完全相反）。"""
    return 1.0 - normalize(matrix) @ normalize(vector)


def distance_ratio_score(d_positive: float, d_negative: float, sharpness: float = 1.0) -> float:
    """
    兩個距離 → 0～100 分：100 × d_neg^s / (d_pos^s + d_neg^s)

    離 positive 越近、離 negative 越遠，分數越高；距離相等時為 50。
    sharpness（s）越大，分數越快往 0 或 100 靠。
    """
    if sharpness <= 0:
        raise ValueError("sharpness must be > 0")
    d_positive = max(float(d_positive), 0.0) ** sharpness
    d_negative = max(float(d_negative), 0.0) ** sharpness
    total = d_positive + d_negative
    if total <= 1e-12:
        return 50.0
    return float(100.0 * d_negative / total)


def check_sharpness(sharpness: float) -> float:
    sharpness = float(sharpness)
    if sharpness <= 0:
        raise ValueError("sharpness must be > 0")
    return sharpness


def check_bank(bank: dict, positive: str, negative: str) -> None:
    for label in (positive, negative):
        if label not in bank or len(bank[label][0]) == 0:
            raise ValueError(f"範例庫缺少類別：{label}")
