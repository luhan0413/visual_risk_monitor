"""
端到端測試：測試替身（影像來源、StubEncoder）+ kNN，驗證整條流程（不需要相機與 GPU）。
"""
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from core.events import EventBus
from core.frame_buffer import FrameBuffer
from core.interfaces import SourceDriver
from core.risk import RiskLeveler
from tests.stubs import StubEncoder
from drivers.scorers.knn import KNNScorer
from services.encoder_service import EncoderService
from services.exemplar_service import ExemplarService
from services.monitor_service import MonitorService
from services.scoring_service import ScoringService
from services.source_service import SourceService

LEVELS = [
    {"name": "LOW", "min": 0, "color": "g"},
    {"name": "MEDIUM", "min": 60, "color": "y"},
    {"name": "HIGH", "min": 85, "color": "r"},
]
GREEN = (40, 200, 40)
RED = (220, 30, 30)


def solid(color):
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    image[:] = color
    return image


class FakeSource(SourceDriver):
    color = GREEN

    def open(self):
        pass

    def close(self):
        pass

    def read(self):
        return solid(FakeSource.color)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.buffer = FrameBuffer(32)
        self.sources = SourceService(self.buffer, factory=lambda name: FakeSource(),
                                     catalog=lambda: [{"name": "fake", "driver": "fake"}], capture_fps=50)
        self.encoders = EncoderService(factory=lambda name: StubEncoder())
        self.exemplars = ExemplarService(Path(self.tmp.name), ("normal", "collision"))
        self.scoring = ScoringService(self.exemplars, self.encoders, "collision", "normal", 2,
                                      factory=lambda name: KNNScorer(k=1))
        self.monitor = MonitorService(self.buffer, self.sources, self.encoders, self.scoring,
                                      RiskLeveler(LEVELS, 1), EventBus(), clip_frames=4,
                                      interval_s=0.05, history_size=100,
                                      stale_after_s=1.0, alert_levels=("MEDIUM", "HIGH"))
        self.encoders.select("stub", background=False)
        self.scoring.select("knn")

    def tearDown(self):
        self.monitor.stop()
        self.sources.stop()
        self.tmp.cleanup()

    def wait_frames(self, n=6):
        deadline = time.time() + 2
        start = self.buffer.latest().index if self.buffer.latest() else -1
        while time.time() < deadline:
            latest = self.buffer.latest()
            if latest and latest.index >= start + n:
                return
            time.sleep(0.01)
        self.fail("source did not produce frames")

    def test_not_ready_without_source(self):
        result = self.monitor.analyze_once()
        self.assertEqual(result.level, "NOT READY")
        self.assertIn("未啟動", result.reason)

    def test_full_flow(self):
        FakeSource.color = GREEN
        self.sources.start("fake")
        self.wait_frames()
        result = self.monitor.analyze_once()
        self.assertFalse(result.ready)
        self.assertIn("範例不足", result.reason)

        for color, label in ((GREEN, "normal"), (RED, "collision")):
            for shade in (0, 10):
                self.exemplars.add(label, [solid(tuple(max(0, c - shade) for c in color))] * 4)

        self.wait_frames()
        green = self.monitor.analyze_once()
        self.assertTrue(green.ready, green.reason)
        self.assertEqual(green.level, "LOW")
        self.assertEqual(green.nearest["label"], "normal")

        FakeSource.color = RED
        self.wait_frames()
        red = self.monitor.analyze_once()
        self.assertEqual(red.level, "HIGH")
        self.assertEqual(red.nearest["label"], "collision")
        self.assertIsNotNone(red.latency_ms)

    def test_current_risk_ready_alert_and_stale(self):
        risk = self.monitor.current_risk()
        self.assertEqual(risk["level"], "NOT READY")
        self.assertIn("未開始", risk["reason"])

        for color, label in ((GREEN, "normal"), (RED, "collision")):
            for shade in (0, 10):
                self.exemplars.add(label, [solid(tuple(max(0, c - shade) for c in color))] * 4)
        FakeSource.color = RED
        self.sources.start("fake")
        self.monitor.start()
        time.sleep(0.5)
        risk = self.monitor.current_risk()
        self.assertTrue(risk["ready"], risk["reason"])
        self.assertEqual(risk["level"], "HIGH")
        self.assertTrue(risk["alert"])
        self.assertFalse(risk["stale"])
        self.assertEqual(risk["source"], "fake")

        # 來源停止後不再有新分析 → 超過門檻變成 STALE，alert 一律 false
        self.sources.stop()
        time.sleep(0.3)
        risk = self.monitor.current_risk(0.2)
        self.assertNotEqual(risk["level"], "HIGH")
        self.assertFalse(risk["alert"])

    def test_current_risk_stale_when_results_stop_updating(self):
        # 模擬分析迴圈仍在、但最後一筆 HIGH 結果已是 5 秒前（例如相機畫面凍結）
        self.monitor._last = {
            "timestamp": time.time() - 5, "level": "HIGH", "score": 95.0, "ready": True,
            "reason": None, "nearest": None,
        }
        with mock.patch.object(MonitorService, "running", new_callable=mock.PropertyMock, return_value=True):
            risk = self.monitor.current_risk(2.0)
            self.assertEqual(risk["level"], "STALE")
            self.assertTrue(risk["stale"])
            self.assertFalse(risk["alert"])
            self.assertGreater(risk["age_s"], 4)

            fresh = self.monitor.current_risk(10.0)
            self.assertEqual(fresh["level"], "HIGH")
            self.assertTrue(fresh["alert"])

    def test_background_loop_records_history(self):
        FakeSource.color = GREEN
        self.sources.start("fake")
        self.monitor.start()
        time.sleep(0.4)
        history = self.monitor.history()
        self.assertGreater(len(history), 0)
        self.assertIn("t", history[-1])

        # 停止後不再提供舊結果
        self.monitor.stop()
        self.assertIsNone(self.monitor.status()["last"])
        risk = self.monitor.current_risk()
        self.assertEqual(risk["level"], "NOT READY")
        self.assertFalse(risk["alert"])


if __name__ == "__main__":
    unittest.main()
