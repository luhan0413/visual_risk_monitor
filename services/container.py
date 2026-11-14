"""
組裝所有 services：從 config_service 取得設定與 driver 工廠，注入各 service。
routes 透過 get_services() 取用。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from core.events import EventBus
from core.frame_buffer import FrameBuffer
from core.risk import RiskLeveler
from services import config_service as cfg
from services.capture_service import CaptureService
from services.encoder_service import EncoderService
from services.exemplar_service import ExemplarService
from services.monitor_service import MonitorService
from services.scoring_service import ScoringService
from services.snapshot_service import SnapshotService
from services.source_service import SourceService

logger = logging.getLogger(__name__)


@dataclass
class Services:
    buffer: FrameBuffer
    events: EventBus
    sources: SourceService
    encoders: EncoderService
    exemplars: ExemplarService
    scoring: ScoringService
    capture: CaptureService
    monitor: MonitorService

    def model_status(self) -> dict[str, Any]:
        return {"encoder": self.encoders.status(), "scorer": self.scoring.status(), **cfg.model_catalog()}


_services: Services | None = None
_lock = threading.Lock()


def build_services() -> Services:
    pipeline = cfg.get("PIPELINE")
    risk = cfg.get("RISK")
    risk_api = cfg.get("RISK_API")
    exemplar_cfg = cfg.get("EXEMPLARS")

    buffer = FrameBuffer(maxlen=pipeline["frame_buffer_size"])
    events = EventBus()
    sources = SourceService(
        buffer,
        factory=cfg.make_source,
        catalog=lambda: [cfg.source_info(name) for name in cfg.source_names()],
        capture_fps=pipeline["capture_fps"],
        stream_fps=pipeline["stream_fps"],
        stream_quality=pipeline["stream_quality"],
    )
    encoders = EncoderService(factory=cfg.make_encoder)
    exemplars = ExemplarService(
        cfg.path("exemplars"),
        cfg.exemplar_labels(),
        frame_jpeg_quality=exemplar_cfg["frame_jpeg_quality"],
        thumbnail_size=exemplar_cfg["thumbnail_size"],
        thumbnail_jpeg_quality=exemplar_cfg["thumbnail_jpeg_quality"],
    )
    scoring = ScoringService(
        exemplars,
        encoders,
        positive=cfg.positive_label(),
        negative=cfg.negative_label(),
        min_per_label=exemplar_cfg["min_per_label"],
        factory=cfg.make_scorer,
    )
    snapshots = SnapshotService(timeout_s=cfg.snapshot_timeout_s())
    capture = CaptureService(
        buffer,
        sources,
        exemplars,
        snapshot_url_for=cfg.snapshot_url,
        fetch_snapshot=snapshots.fetch,
    )
    monitor = MonitorService(
        buffer,
        sources,
        encoders,
        scoring,
        RiskLeveler(risk["levels"], risk["smoothing_window"], risk["not_ready_color"]),
        events,
        clip_frames=pipeline["clip_frames"],
        interval_s=pipeline["analysis_interval_s"],
        history_size=pipeline["history_size"],
        stale_after_s=risk_api["stale_after_s"],
        alert_levels=risk_api["alert_levels"],
    )
    return Services(buffer, events, sources, encoders, exemplars, scoring, capture, monitor)


def get_services() -> Services:
    global _services
    with _lock:
        if _services is None:
            _services = build_services()
        return _services


def pipeline_autostart() -> bool:
    return bool(cfg.get("PIPELINE").get("autostart_analysis", False))


def init_services() -> Services:
    """啟動時呼叫：檢查設定、選定預設模型與評分方法。分析預設要在網頁按「開始分析」才會開始。"""
    for problem in cfg.validate():
        logger.warning("設定問題：%s", problem)
    services = get_services()
    services.scoring.select(cfg.get("DEFAULT_SCORER"))
    services.encoders.select(cfg.get("DEFAULT_ENCODER"), background=True)
    if pipeline_autostart():
        services.monitor.start()
    logger.info("services ready: encoder=%s scorer=%s", cfg.get("DEFAULT_ENCODER"), cfg.get("DEFAULT_SCORER"))
    return services
