"""
即時分析服務：定時取最近一段影格 → encoder → scorer → 分級，結果推送到前端。

這一層只透過 services 與 core 介面運作，不知道底下用的是哪個相機或模型。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from core.events import EventBus
from core.frame_buffer import FrameBuffer
from core.risk import RiskLeveler
from core.types import RiskAssessment, ScoreResult
from services.encoder_service import EncoderService
from services.scoring_service import ScoringService
from services.source_service import SourceService


class MonitorService:
    def __init__(
        self,
        buffer: FrameBuffer,
        sources: SourceService,
        encoders: EncoderService,
        scoring: ScoringService,
        leveler: RiskLeveler,
        events: EventBus,
        clip_frames: int,
        interval_s: float,
        history_size: int,
    ):
        self.buffer = buffer
        self.sources = sources
        self.encoders = encoders
        self.scoring = scoring
        self.leveler = leveler
        self.events = events
        self.clip_frames = int(clip_frames)
        self.interval_s = float(interval_s)
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._session_id: int | None = None
        self._session_start: float | None = None
        self._last_frame_index: int | None = None
        self._last: dict[str, Any] | None = None

    # ---------- lifecycle ----------

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> dict[str, Any]:
        if not self.running:
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="monitor", daemon=True)
            self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "interval_s": self.interval_s,
            "clip_frames": self.clip_frames,
            "history": len(self._history),
            "last": self._last,
        }

    def current_risk(self, stale_after_s: float, alert_levels: list[str] | tuple[str, ...]) -> dict[str, Any]:
        """
        給外部系統查詢的精簡結果。

        level 只會是設定的等級（LOW / MEDIUM / HIGH）或 NOT READY / STALE。
        呼叫端應把 NOT READY 與 STALE 視為「不知道」，不能當作安全。
        """
        now = time.time()
        last = self._last
        source = self.sources.status()
        result: dict[str, Any] = {
            "level": "NOT READY",
            "score": None,
            "alert": False,
            "ready": False,
            "stale": False,
            "age_s": None,
            "reason": None,
            "timestamp": None,
            "source": source.get("source_name"),
            "nearest": None,
            "server_time": now,
        }
        if not self.running:
            result["reason"] = "分析已暫停"
            return result
        if last is None:
            result["reason"] = "尚未有分析結果"
            return result

        age = now - last["timestamp"]
        result.update(
            level=last["level"],
            score=last["score"],
            ready=bool(last["ready"]),
            age_s=round(age, 2),
            reason=last["reason"],
            timestamp=last["timestamp"],
            nearest=last["nearest"],
        )
        if age > stale_after_s:
            result.update(level="STALE", ready=False, stale=True,
                          reason=f"最後一次分析已是 {age:.1f} 秒前（來源停止或分析延遲）")
        result["alert"] = result["ready"] and result["level"] in alert_levels
        return result

    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history)

    def reset(self) -> None:
        with self._lock:
            self._history.clear()
        self.leveler.reset()
        self._last_frame_index = None
        self._session_start = time.time()
        self.events.publish("reset", {"session_id": self._session_id})

    # ---------- analysis ----------

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                assessment = self.analyze_once()
            except Exception as exc:  # noqa: BLE001 - 分析失敗不能讓迴圈停掉
                assessment = self._assess(ScoreResult.not_ready(f"分析錯誤：{exc}"), None, None)
            if assessment is not None:
                self._record(assessment)
            self._stop.wait(max(0.0, self.interval_s - (time.monotonic() - started)))

    def _assess(self, result: ScoreResult, latency_ms: float | None, frame_index: int | None) -> RiskAssessment:
        smoothed, level = self.leveler.update(result.score)
        return RiskAssessment(
            timestamp=time.time(),
            raw_score=None if result.score is None else round(result.score, 2),
            score=None if smoothed is None else round(smoothed, 2),
            level=level["name"],
            color=level["color"],
            ready=result.ready,
            reason=result.reason,
            nearest=result.nearest,
            latency_ms=latency_ms,
            encoder=self.encoders.name,
            scorer=self.scoring.name,
            frame_index=frame_index,
        )

    def analyze_once(self) -> RiskAssessment | None:
        """執行一次分析。影像沒有更新時回傳 None（不記錄）。"""
        if self.sources.session_id != self._session_id:
            self._session_id = self.sources.session_id
            self.reset()

        if not self.sources.running:
            return self._assess(ScoreResult.not_ready("影像來源未啟動"), None, None)

        clip = self.buffer.clip(self.clip_frames)
        if len(clip) < self.clip_frames:
            return self._assess(ScoreResult.not_ready(f"影格累積中 {len(clip)}/{self.clip_frames}"), None, None)

        frame_index = clip[-1].index
        if frame_index == self._last_frame_index:
            return None  # 來源沒有新畫面（例如回放結束）
        self._last_frame_index = frame_index

        if not self.encoders.ready:
            status = self.encoders.status()
            reason = f"模型{'載入中' if status['state'] == 'loading' else '未就緒'}"
            if status.get("error"):
                reason += f"：{status['error']}"
            return self._assess(ScoreResult.not_ready(reason), None, frame_index)

        started = time.monotonic()
        embedding = self.encoders.encode([frame.image for frame in clip])
        result = self.scoring.score(embedding)
        latency_ms = round((time.monotonic() - started) * 1000, 1)
        return self._assess(result, latency_ms, frame_index)

    def _record(self, assessment: RiskAssessment) -> None:
        data = assessment.to_dict()
        start = self._session_start or assessment.timestamp
        data["t"] = round(assessment.timestamp - start, 2)  # 時間軸用：本次來源啟動後的秒數
        with self._lock:
            self._history.append(data)
        self._last = data
        self.events.publish("risk", data)
