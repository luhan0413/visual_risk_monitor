"""影像編碼 / 解碼（主系統上傳範例與 Model Server 共用）。"""
from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np


def decode_image(data: bytes, name: str = "image") -> np.ndarray:
    """JPEG / PNG bytes → RGB uint8。"""
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"無法解碼影像：{name}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def decode_images(files: Iterable[tuple[str, bytes]], max_count: int | None = None) -> list[np.ndarray]:
    """files: [(檔名, bytes), ...]，依順序解碼。"""
    files = list(files)
    if not files:
        raise ValueError("沒有影像")
    if max_count is not None and len(files) > max_count:
        raise ValueError(f"影像最多 {max_count} 張")
    return [decode_image(data, name) for name, data in files]
