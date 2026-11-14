"""
通用串流來源：只要一個 URL，不需要知道背後是哪種相機。

依回應自動判斷格式：
    multipart/x-mixed-replace（MJPEG 串流） 持續讀取，保留最新一張
    image/jpeg、image/png（單張影像）       反覆 GET 輪詢
    rtsp:// 等其他協定                     交給 OpenCV VideoCapture

背景執行緒負責接收並只保留最新一張，所以分析永遠拿到最新畫面，不會累積延遲。
斷線時自動重連。
"""
from __future__ import annotations

import threading
import time
from typing import Any

import cv2
import numpy as np
import requests

from core.interfaces import SourceDriver

_SOI = b"\xff\xd8"  # JPEG 開頭
_EOI = b"\xff\xd9"  # JPEG 結尾
_MAX_BUFFER = 8 * 1024 * 1024


class HTTPStreamSource(SourceDriver):
    def __init__(
        self,
        url: str,
        timeout_s: float = 5.0,
        reconnect_s: float = 1.0,
        snapshot_fps: float = 15.0,
        headers: dict[str, str] | None = None,
    ):
        if not isinstance(url, str) or not url.strip():
            raise ValueError("url must be a non-empty string")
        self.url = url.strip()
        self.timeout_s = float(timeout_s)
        self.reconnect_s = float(reconnect_s)
        self.snapshot_fps = float(snapshot_fps)
        self.headers = headers or {}

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._session: requests.Session | None = None
        self._latest: bytes | np.ndarray | None = None  # JPEG bytes 或已解碼的 RGB
        self._latest_seq = 0
        self._decoded_seq = -1
        self._decoded: np.ndarray | None = None
        self._first_frame = threading.Event()

        self.mode: str | None = None
        self._connected = False
        self._last_error: str | None = None
        self._frames = 0
        self._reconnects = 0
        self._last_frame_time: float | None = None

    # ---------- lifecycle ----------

    def open(self) -> None:
        self._stop.clear()
        self._first_frame.clear()
        self._session = requests.Session()
        self._thread = threading.Thread(target=self._run, name="http-stream", daemon=True)
        self._thread.start()
        if not self._first_frame.wait(self.timeout_s):
            error = self._last_error or f"{self.timeout_s} 秒內沒有收到影像"
            self.close()
            raise RuntimeError(f"無法取得串流 {self.url}：{error}")

    def close(self) -> None:
        self._stop.set()
        if self._session is not None:
            self._session.close()  # 中斷阻塞中的串流讀取
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=self.timeout_s + 1)
        self._thread = None
        self._session = None
        self._connected = False

    def read(self) -> np.ndarray | None:
        with self._lock:
            latest, seq = self._latest, self._latest_seq
        if latest is None:
            return None
        if seq != self._decoded_seq:
            if isinstance(latest, np.ndarray):
                image = latest
            else:
                bgr = cv2.imdecode(np.frombuffer(latest, dtype=np.uint8), cv2.IMREAD_COLOR)
                if bgr is None:
                    return self._decoded  # 壞掉的一張：沿用上一張
                image = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            self._decoded, self._decoded_seq = image, seq
        return self._decoded

    def status(self) -> dict[str, Any]:
        age = time.time() - self._last_frame_time if self._last_frame_time else None
        return {
            "url": self.url,
            "mode": self.mode,
            "connected": self._connected,
            "frames_received": self._frames,
            "last_frame_age_s": round(age, 2) if age is not None else None,
            "reconnects": self._reconnects,
            "last_error": self._last_error,
        }

    # ---------- receiving ----------

    def _publish(self, frame: bytes | np.ndarray) -> None:
        with self._lock:
            self._latest = frame
            self._latest_seq += 1
        self._frames += 1
        self._last_frame_time = time.time()
        self._last_error = None
        self._first_frame.set()

    def _run(self) -> None:
        first = True
        while not self._stop.is_set():
            if not first:
                self._reconnects += 1
                self._stop.wait(self.reconnect_s)
                if self._stop.is_set():
                    break
            first = False
            try:
                if self.url.lower().startswith(("http://", "https://")):
                    self._run_http()
                else:
                    self._run_opencv()
            except Exception as exc:  # noqa: BLE001 - 記錄後重連
                if not self._stop.is_set():
                    self._last_error = f"{type(exc).__name__}: {exc}"
            finally:
                self._connected = False

    def _run_http(self) -> None:
        assert self._session is not None
        reply = self._session.get(self.url, stream=True, timeout=self.timeout_s, headers=self.headers)
        reply.raise_for_status()
        content_type = reply.headers.get("Content-Type", "").lower()
        self._connected = True

        if content_type.startswith("multipart/"):
            self.mode = "mjpeg"
            self._read_mjpeg(reply)
        elif content_type.startswith("image/"):
            self.mode = "snapshot"
            self._publish(reply.content)
            self._poll_snapshots()
        else:
            reply.close()
            raise RuntimeError(f"不支援的串流格式：{content_type or '未知'}")

    def _read_mjpeg(self, reply: requests.Response) -> None:
        buffer = bytearray()
        for chunk in reply.iter_content(chunk_size=32 * 1024):
            if self._stop.is_set():
                break
            if not chunk:
                continue
            buffer.extend(chunk)
            latest = None
            # 取出 buffer 裡所有完整的 JPEG，只保留最後一張
            while True:
                start = buffer.find(_SOI)
                if start < 0:
                    buffer.clear()
                    break
                end = buffer.find(_EOI, start + 2)
                if end < 0:
                    if start > 0:
                        del buffer[:start]
                    break
                latest = bytes(buffer[start:end + 2])
                del buffer[:end + 2]
            if latest is not None:
                self._publish(latest)
            if len(buffer) > _MAX_BUFFER:
                buffer.clear()
        if not self._stop.is_set():
            raise RuntimeError("串流已中斷")

    def _poll_snapshots(self) -> None:
        assert self._session is not None
        period = 1.0 / max(self.snapshot_fps, 0.1)
        while not self._stop.is_set():
            started = time.monotonic()
            reply = self._session.get(self.url, timeout=self.timeout_s, headers=self.headers)
            reply.raise_for_status()
            self._publish(reply.content)
            self._stop.wait(max(0.0, period - (time.monotonic() - started)))

    def _run_opencv(self) -> None:
        self.mode = "opencv"
        capture = cv2.VideoCapture(self.url)
        try:
            if not capture.isOpened():
                raise RuntimeError("OpenCV 無法開啟串流")
            self._connected = True
            while not self._stop.is_set():
                ok, image = capture.read()
                if not ok or image is None:
                    raise RuntimeError("串流讀取失敗")
                self._publish(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        finally:
            capture.release()
