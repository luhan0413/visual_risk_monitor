import unittest

import numpy as np

from core.events import EventBus
from core.frame_buffer import FrameBuffer
from core.risk import NOT_READY_LEVEL, RiskLeveler
from core.types import Frame

LEVELS = [
    {"name": "LOW", "min": 0, "color": "g"},
    {"name": "MEDIUM", "min": 60, "color": "y"},
    {"name": "HIGH", "min": 85, "color": "r"},
]


class RiskLevelerTest(unittest.TestCase):
    def test_classify_boundaries(self):
        leveler = RiskLeveler(LEVELS)
        self.assertEqual(leveler.classify(0)["name"], "LOW")
        self.assertEqual(leveler.classify(59.9)["name"], "LOW")
        self.assertEqual(leveler.classify(60)["name"], "MEDIUM")
        self.assertEqual(leveler.classify(85)["name"], "HIGH")
        self.assertIs(leveler.classify(None), NOT_READY_LEVEL)

    def test_smoothing_and_reset_on_none(self):
        leveler = RiskLeveler(LEVELS, smoothing_window=3)
        leveler.update(30)
        leveler.update(60)
        score, level = leveler.update(90)
        self.assertAlmostEqual(score, 60)
        self.assertEqual(level["name"], "MEDIUM")
        score, level = leveler.update(None)
        self.assertIsNone(score)
        score, _ = leveler.update(90)
        self.assertAlmostEqual(score, 90)  # None 之後重新開始平均


class FrameBufferTest(unittest.TestCase):
    def test_clip_returns_latest(self):
        buffer = FrameBuffer(maxlen=4)
        for i in range(6):
            buffer.push(Frame(np.zeros((2, 2, 3), np.uint8), float(i), i))
        self.assertEqual(len(buffer), 4)
        self.assertEqual([f.index for f in buffer.clip(3)], [3, 4, 5])
        self.assertEqual(buffer.latest().index, 5)


class EventBusTest(unittest.TestCase):
    def test_full_queue_drops_oldest(self):
        bus = EventBus(queue_size=2)
        q = bus.subscribe()
        for i in range(3):
            bus.publish("risk", i)
        self.assertEqual([q.get_nowait()[1], q.get_nowait()[1]], [1, 2])
        bus.unsubscribe(q)
        bus.publish("risk", 9)
        self.assertTrue(q.empty())


if __name__ == "__main__":
    unittest.main()
