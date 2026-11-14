"""
拍照測試：CaptureService（暫存資料夾，不影響真正的範例庫）與 SnapshotService（本機測試用 API）。
"""
import tempfile
import threading
import time
import unittest
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response
from werkzeug.serving import make_server

from core.frame_buffer import FrameBuffer
from core.types import Frame
from services.capture_service import CaptureService
from services.exemplar_service import ExemplarService
from services.snapshot_service import SnapshotService


class SourcesStub:
    def __init__(self, name="cam", running=True):
        self.name, self.running = name, running

    def status(self):
        return {"source_name": self.name}


class CaptureServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.buffer = FrameBuffer(8)
        self.exemplars = ExemplarService(Path(self.tmp.name), ("normal", "collision"))
        self.fetched = []

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, snapshot_url=None, running=True):
        def fetch(url):
            self.fetched.append(url)
            return np.full((60, 80, 3), 200, np.uint8)
        return CaptureService(self.buffer, SourcesStub(running=running), self.exemplars,
                              snapshot_url_for=lambda name: snapshot_url, fetch_snapshot=fetch)

    def test_uses_snapshot_api_when_configured(self):
        info = self.make("http://cam/snapshot").capture_current("collision")
        self.assertEqual(self.fetched, ["http://cam/snapshot"])
        self.assertEqual(info["capture"], "snapshot_api")
        self.assertEqual(info["frame_count"], 1)
        self.assertEqual(self.exemplars.counts()["collision"], 1)

    def test_falls_back_to_stream_frame(self):
        self.buffer.push(Frame(np.zeros((48, 64, 3), np.uint8), time.time(), 7))
        info = self.make(None).capture_current("normal")
        self.assertEqual(self.fetched, [])
        self.assertEqual(info["capture"], "stream_frame")
        self.assertEqual(info["source_frame_index"], 7)

    def test_requires_running_source(self):
        with self.assertRaisesRegex(ValueError, "開啟影像來源"):
            self.make("http://cam/snapshot", running=False).capture_current("normal")
        self.assertEqual(self.fetched, [])

    def test_rejects_unknown_label_before_fetching(self):
        with self.assertRaises(ValueError):
            self.make("http://cam/snapshot").capture_current("unknown")
        self.assertEqual(self.fetched, [])


class SnapshotServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = Flask(__name__)
        jpeg = cv2.imencode(".jpg", np.full((48, 64, 3), (255, 0, 0), np.uint8))[1].tobytes()  # BGR 藍色

        @app.route("/image")
        def image():
            return Response(jpeg, mimetype="image/jpeg")

        @app.route("/text")
        def text():
            return "not an image"

        @app.route("/broken")
        def broken():
            return Response(b"garbage", mimetype="image/jpeg")

        cls.server = make_server("127.0.0.1", 0, app, threaded=True)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_fetch_image(self):
        image = SnapshotService(timeout_s=2).fetch(self.base + "/image")
        self.assertEqual(image.shape, (48, 64, 3))
        self.assertGreater(image[0, 0, 2], 200)  # RGB 的 B

    def test_errors(self):
        service = SnapshotService(timeout_s=0.5)
        with self.assertRaisesRegex(RuntimeError, "不是影像"):
            service.fetch(self.base + "/text")
        with self.assertRaisesRegex(RuntimeError, "無法解碼"):
            service.fetch(self.base + "/broken")
        with self.assertRaisesRegex(RuntimeError, "無法取得照片"):
            service.fetch("http://127.0.0.1:9/image")


if __name__ == "__main__":
    unittest.main()
