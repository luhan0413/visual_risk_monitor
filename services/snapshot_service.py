"""拍照：呼叫相機的拍照 API（snapshot_url），取得一張照片。"""
from __future__ import annotations

import numpy as np
import requests

from services.image_codec import decode_image


class SnapshotService:
    def __init__(self, timeout_s: float = 5.0):
        self.timeout_s = float(timeout_s)
        self._session = requests.Session()

    def fetch(self, url: str) -> np.ndarray:
        """回傳 RGB 影像。連線失敗或回傳的不是影像時 raise RuntimeError。"""
        try:
            reply = self._session.get(url, timeout=self.timeout_s)
            reply.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"拍照 API 無法取得照片：{exc}") from exc
        content_type = reply.headers.get("Content-Type", "").lower()
        if not content_type.startswith("image/"):
            raise RuntimeError(f"拍照 API 回傳的不是影像（{content_type or '未知格式'}）")
        try:
            return decode_image(reply.content, url)
        except ValueError as exc:
            raise RuntimeError(f"拍照 API 回傳的影像無法解碼：{url}") from exc
