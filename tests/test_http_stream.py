"""
HTTPStreamSource 測試：用本機假的串流 API（MJPEG 與單張 JPEG）驗證，不需要相機。
"""
import threading
import time
import unittest

import cv2
import numpy as np
from flask import Flask, Response
from werkzeug.serving import make_server

from drivers.sources.http_stream import HTTPStreamSource


def jpeg(color):
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    image[:] = color  # BGR
    return cv2.imencode(".jpg", image)[1].tobytes()


RED, BLUE = jpeg((0, 0, 255)), jpeg((255, 0, 0))


def make_app():
    app = Flask(__name__)
    state = {"color": RED}

    @app.route("/mjpeg")
    def mjpeg():
        def generate():
            for _ in range(2000):
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + state["color"] + b"\r\n"
                time.sleep(0.01)
        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/snapshot")
    def snapshot():
        return Response(state["color"], mimetype="image/jpeg")

    @app.route("/text")
    def text():
        return "hello"

    return app, state


class HTTPStreamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app, cls.state = make_app()
        cls.server = make_server("127.0.0.1", 0, app, threaded=True)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.state["color"] = RED

    def wait_color(self, source, channel, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            image = source.read()
            if image is not None and image[0, 0, channel] > 200:
                return image
            time.sleep(0.02)
        self.fail(f"沒有收到預期顏色，status={source.status()}")

    def check_stream(self, path, mode):
        source = HTTPStreamSource(self.base + path, timeout_s=2)
        source.open()
        try:
            self.assertEqual(source.status()["mode"], mode)
            self.wait_color(source, 0)  # RGB 的 R
            self.state["color"] = BLUE
            self.wait_color(source, 2)  # 畫面更新後拿到最新一張
            self.assertGreater(source.status()["frames_received"], 1)
        finally:
            source.close()

    def test_mjpeg(self):
        self.check_stream("/mjpeg", "mjpeg")

    def test_snapshot_polling(self):
        self.check_stream("/snapshot", "snapshot")

    def test_unreachable_raises(self):
        with self.assertRaisesRegex(RuntimeError, "無法取得串流"):
            HTTPStreamSource("http://127.0.0.1:9/stream", timeout_s=0.5).open()

    def test_unsupported_content_type(self):
        with self.assertRaisesRegex(RuntimeError, "不支援的串流格式"):
            HTTPStreamSource(self.base + "/text", timeout_s=0.5).open()

    def test_config_with_only_url(self):
        import config
        from services import config_service

        original = dict(config.SOURCES)
        config.SOURCES["test_cam"] = {"url": self.base + "/mjpeg", "timeout_s": 2}
        try:
            source = config_service.make_source("test_cam")
            self.assertIsInstance(source, HTTPStreamSource)
            self.assertEqual(source.timeout_s, 2)  # 個別設定覆寫預設值
            self.assertEqual(source.reconnect_s, config.STREAM_DEFAULTS["reconnect_s"])  # 其餘套用預設值
        finally:
            config.SOURCES.clear()
            config.SOURCES.update(original)


if __name__ == "__main__":
    unittest.main()
