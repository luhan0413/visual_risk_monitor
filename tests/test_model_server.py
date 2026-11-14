"""
Model server 與 remote_http encoder 的整合測試（使用測試替身 StubEncoder，不需要 GPU）。
"""
import threading
import unittest

import numpy as np
from werkzeug.serving import make_server

from tests.stubs import StubEncoder
from drivers.encoders.remote_http import RemoteHTTPEncoder
from model_server.main import create_app
from model_server.service import ModelServerService
from services.encoder_service import EncoderService


def frames(color, n=4):
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    image[:] = color
    image[100:200, 100:300] = (255, 255, 255)
    return [image] * n


class ModelServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoders = EncoderService(factory=lambda name: StubEncoder())
        cls.server = make_server("127.0.0.1", 0, create_app(ModelServerService(cls.encoders, max_frames=64)),
                                 threaded=True)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.encoders.unload()

    def test_remote_load_and_encode(self):
        remote = RemoteHTTPEncoder(self.base_url, "stub", connect_wait_s=2, load_timeout_s=5)
        remote.load()  # model server 尚未載入 → remote 會要求載入並等待完成
        self.assertEqual(self.encoders.name, "stub")
        self.assertTrue(self.encoders.ready)

        clip = frames((30, 120, 200))
        vector = remote.encode(clip)
        local = StubEncoder().encode(clip)
        self.assertEqual(vector.shape, local.shape)
        cosine = float(vector @ local / (np.linalg.norm(vector) * np.linalg.norm(local)))
        self.assertGreater(cosine, 0.95)  # 經過縮圖與 JPEG，結果應幾乎相同

    def test_encode_rejects_wrong_model(self):
        self.encoders.select("stub", background=False)
        remote = RemoteHTTPEncoder(self.base_url, "other_model")
        with self.assertRaises(RuntimeError):
            remote.encode(frames((0, 0, 0), 2))

    def test_unreachable_server(self):
        remote = RemoteHTTPEncoder("http://127.0.0.1:9", "stub", connect_wait_s=0, timeout_s=0.5)
        with self.assertRaisesRegex(RuntimeError, "無法連線"):
            remote.load()


if __name__ == "__main__":
    unittest.main()
