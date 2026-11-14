"""
影像來源服務：管理目前使用的 SourceDriver，背景執行緒持續把影格放進 FrameBuffer。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Iterator

import cv2

import config
from core.frame_buffer import FrameBuffer
from core.interfaces import SourceDriver
from core.types import Frame
from drivers import loader


class SourceService:
    def __init__(
        self,
        buffer: FrameBuffer,
        capture_fps: float,
        stream_fps: float = 15.0,
        stream_quality: int = 80,
        factory: Callable[[str], SourceDriver] = loader.create_source,
        source_names: list[str] | None = None,
    ):
        self.buffer = buffer
        self.capture_fps = float(capture_fps)
        self.stream_fps = float(stream_fps)
        self.stream_quality = int(stream_quality)
        self._factory = factory
        self._source_names = source_names if source_names is not None else list(config.SOURCES)
        self._lock = threading.RLock()
        self._driver: SourceDriver | None = None
        self._source_name: str | None = None
        self._options: dict[str, Any] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state = "idle"
        self._error: str | None = None
        self._frame_index = 0
        self._started_at: float | None = None
        self.session_id = 0  # 每次啟動來源 +1，monitor 用來重置時間軸

    # ---------- query ----------

    def list_sources(self) -> list[dict[str, Any]]:
        result = []
        for name in self._source_names:
            entry = config.SOURCES.get(name, {})
            item = {"name": name, "driver": loader.source_driver_name(entry), "url": entry.get("url"), "options": {}}
            try:
                item["options"] = self._factory(name).options()  # 只建立物件，不會連線
            except Exception as exc:  # noqa: BLE001
                item["error"] = str(exc)
            result.append(item)
        return result

    @property
    def running(self) -> bool:
        return self._state == "running"

    def status(self) -> dict[str, Any]:
        with self._lock:
            elapsed = time.time() - self._started_at if self._started_at else None
            return {
                "state": self._state,
                "source_name": self._source_name,
                "options": self._options,
                "error": self._error,
                "frames": self._frame_index,
                "buffered": len(self.buffer),
                "elapsed_s": round(elapsed, 1) if elapsed else None,
                "session_id": self.session_id,
                "driver": self._driver.status() if self._driver else None,
            }

    # ---------- lifecycle ----------

    def start(self, source_name: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        self.stop()  # 在取得 lock 之前停止舊來源，避免 join 時與擷取執行緒互卡
        with self._lock:
            driver = self._factory(source_name)
            driver.configure(**options)
            try:
                driver.open()
            except Exception as exc:
                self._state, self._error = "error", str(exc)
                raise
            self._driver = driver
            self._source_name = source_name
            self._options = options
            self._state, self._error = "running", None
            self._frame_index = 0
            self._started_at = time.time()
            self.session_id += 1
            self.buffer.clear()
            self._stop.clear()
            self._thread = threading.Thread(target=self._capture_loop, name="source-capture", daemon=True)
            self._thread.start()
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop.set()
            thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        with self._lock:
            if self._driver is not None:
                self._driver.close()
                self._driver = None
            if self._state == "running":
                self._state = "idle"
            return self.status()

    def _capture_loop(self) -> None:
        period = 1.0 / max(self.capture_fps, 0.1)
        next_tick = time.monotonic()
        while not self._stop.is_set():
            driver = self._driver
            if driver is None:
                break
            try:
                image = driver.read()
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._state, self._error = "error", str(exc)
                break
            if image is not None:
                self.buffer.push(Frame(image=image, timestamp=time.time(), index=self._frame_index))
                self._frame_index += 1
            next_tick += period
            delay = next_tick - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_tick = time.monotonic()

    # ---------- preview ----------

    def latest_jpeg(self, quality: int | None = None) -> bytes | None:
        frame = self.buffer.latest()
        if frame is None:
            return None
        bgr = cv2.cvtColor(frame.image, cv2.COLOR_RGB2BGR)
        ok, encoded = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality or self.stream_quality])
        return encoded.tobytes() if ok else None

    def mjpeg_stream(self) -> Iterator[bytes]:
        period = 1.0 / max(self.stream_fps, 0.1)
        last_index = None
        while True:
            frame = self.buffer.latest()
            if frame is not None and frame.index != last_index:
                last_index = frame.index
                jpeg = self.latest_jpeg()
                if jpeg:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(period)
