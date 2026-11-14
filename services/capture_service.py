"""
範例拍照：把一張照片存進範例庫。

    來源有設定 snapshot_url（拍照 API） → 呼叫拍照 API 取得照片
    沒有設定（例如錄影回放）           → 存目前串流畫面
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from core.frame_buffer import FrameBuffer
from services.exemplar_service import ExemplarService
from services.source_service import SourceService


class CaptureService:
    def __init__(
        self,
        buffer: FrameBuffer,
        sources: SourceService,
        exemplars: ExemplarService,
        snapshot_url_for: Callable[[str | None], str | None],
        fetch_snapshot: Callable[[str], np.ndarray],
    ):
        """
        snapshot_url_for: 來源名稱 → 拍照 API 網址（沒有則 None）
        fetch_snapshot:   拍照 API 網址 → RGB 影像
        """
        self.buffer = buffer
        self.sources = sources
        self.exemplars = exemplars
        self._snapshot_url_for = snapshot_url_for
        self._fetch_snapshot = fetch_snapshot

    def capture_current(self, label: str, note: str = "") -> dict[str, Any]:
        self.exemplars.check_label(label)
        if not self.sources.running:
            raise ValueError("請先開啟影像來源")
        source_name = self.sources.status().get("source_name")

        url = self._snapshot_url_for(source_name)
        if url:
            image = self._fetch_snapshot(url)
            meta = {"source": source_name, "capture": "snapshot_api", "snapshot_url": url, "note": note}
        else:
            frame = self.buffer.latest()
            if frame is None:
                raise ValueError("目前沒有影像")
            image = frame.image
            meta = {"source": source_name, "capture": "stream_frame", "source_frame_index": frame.index, "note": note}
        return self.exemplars.add(label, [image], meta)
