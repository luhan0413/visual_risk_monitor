"""
組裝所有 services（依 config 建立，routes 透過 get_services() 取用）。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import config
from core.events import EventBus
from core.frame_buffer import FrameBuffer
from core.risk import RiskLeveler
from services.encoder_service import EncoderService
from services.exemplar_service import ExemplarService
from services.monitor_service import MonitorService
from services.scoring_service import ScoringService
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
    monitor: MonitorService


_services: Services | None = None
_lock = threading.Lock()


def build_services() -> Services:
    pipeline = config.PIPELINE
    buffer = FrameBuffer(maxlen=max(pipeline["clip_frames"] * 2, 32))
    events = EventBus()
    sources = SourceService(
        buffer,
        capture_fps=pipeline["capture_fps"],
        stream_fps=pipeline["stream_fps"],
        stream_quality=pipeline["stream_quality"],
    )
    encoders = EncoderService()
    exemplars = ExemplarService(config.EXEMPLAR_DIR, config.EXEMPLAR_LABELS)
    scoring = ScoringService(
        exemplars,
        encoders,
        positive=config.POSITIVE_LABEL,
        negative=config.NEGATIVE_LABEL,
        min_per_label=config.MIN_EXEMPLARS_PER_LABEL,
    )
    monitor = MonitorService(
        buffer,
        sources,
        encoders,
        scoring,
        RiskLeveler(config.RISK["levels"], config.RISK["smoothing_window"]),
        events,
        clip_frames=pipeline["clip_frames"],
        interval_s=pipeline["analysis_interval_s"],
        history_size=pipeline["history_size"],
    )
    return Services(buffer, events, sources, encoders, exemplars, scoring, monitor)


def get_services() -> Services:
    global _services
    with _lock:
        if _services is None:
            _services = build_services()
        return _services


def init_services() -> Services:
    """啟動時呼叫：選定預設模型與評分方法，啟動分析迴圈（影像來源由使用者在介面上開啟）。"""
    services = get_services()
    services.scoring.select(config.DEFAULT_SCORER)
    services.encoders.select(config.DEFAULT_ENCODER, background=True)
    services.monitor.start()
    logger.info("services ready: encoder=%s scorer=%s", config.DEFAULT_ENCODER, config.DEFAULT_SCORER)
    return services
