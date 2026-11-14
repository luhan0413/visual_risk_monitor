"""
回放錄影檔。

依實際經過的時間對應影片時間（跟即時串流一樣的節奏），
所以分析結果的時間軸可以直接對照影片秒數。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from core.interfaces import SourceDriver

VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


class VideoFileSource(SourceDriver):
    def __init__(self, video_dir: str, loop: bool = True):
        self.video_dir = Path(video_dir)
        self.loop = bool(loop)
        self.video: str | None = None
        self._capture: cv2.VideoCapture | None = None
        self._fps = 0.0
        self._frame_count = 0
        self._position = -1  # 目前已讀到的影格
        self._start_time = 0.0
        self._last_image: np.ndarray | None = None
        self.ended = False

    # ---------- options ----------

    def list_videos(self) -> list[str]:
        if not self.video_dir.is_dir():
            return []
        return sorted(
            str(path.relative_to(self.video_dir))
            for path in self.video_dir.rglob("*")
            if path.suffix.lower() in VIDEO_SUFFIXES and path.is_file()
        )

    def options(self) -> dict[str, Any]:
        return {"videos": self.list_videos()}

    def configure(self, video: str | None = None, loop: bool | None = None, **kwargs: Any) -> None:
        super().configure(**kwargs)
        if loop is not None:
            self.loop = bool(loop)
        if video is not None:
            if video not in self.list_videos():
                raise ValueError(f"找不到影片：{video}")
            self.video = video

    # ---------- lifecycle ----------

    def open(self) -> None:
        if self.video is None:
            videos = self.list_videos()
            if not videos:
                raise RuntimeError(f"{self.video_dir} 裡沒有影片")
            self.video = videos[0]
        capture = cv2.VideoCapture(str(self.video_dir / self.video))
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"無法開啟影片：{self.video}")
        self._capture = capture
        self._fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        self._frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        self._rewind()

    def _rewind(self) -> None:
        assert self._capture is not None
        self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self._position = -1
        self._start_time = time.monotonic()
        self._last_image = None
        self.ended = False

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def read(self) -> np.ndarray | None:
        if self._capture is None or self.ended:
            return None
        target = int((time.monotonic() - self._start_time) * self._fps)
        while self._position < target:
            ok = self._capture.grab()
            if not ok:
                if self.loop and self._position >= 0:
                    last = self._last_image
                    self._rewind()  # 下一次 read() 從頭開始
                    return last
                self.ended = True
                return None
            self._position += 1
            if self._position == target:
                ok, image = self._capture.retrieve()
                if ok:
                    self._last_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return self._last_image

    def status(self) -> dict[str, Any]:
        return {
            "video": self.video,
            "fps": self._fps,
            "frame_count": self._frame_count,
            "position": self._position,
            "position_s": round(self._position / self._fps, 2) if self._fps else None,
            "loop": self.loop,
            "ended": self.ended,
        }
