import tempfile
import unittest
from pathlib import Path

import numpy as np

from services.exemplar_service import ExemplarService


def image(value):
    return np.full((48, 64, 3), value, dtype=np.uint8)


class ExemplarServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = ExemplarService(Path(self.tmp.name), ("normal", "collision"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_list_delete(self):
        info = self.service.add("collision", [image(10), image(20)], {"source": "test"})
        self.assertEqual(info["frame_count"], 2)
        self.assertEqual(self.service.counts(), {"normal": 0, "collision": 1})
        self.assertTrue(self.service.thumbnail_path(info["id"]).exists())
        self.assertEqual(len(self.service.load_frames(info["id"])), 2)
        version = self.service.version
        self.service.delete(info["id"])
        self.assertEqual(self.service.counts()["collision"], 0)
        self.assertGreater(self.service.version, version)

    def test_rejects_bad_label_and_id(self):
        with self.assertRaises(ValueError):
            self.service.add("unknown", [image(0)])
        with self.assertRaises(ValueError):
            self.service.delete("../../etc")
        with self.assertRaises(FileNotFoundError):
            self.service.delete("normal-20260101-000000-abcdef")

    def test_embedding_cache_per_encoder(self):
        info = self.service.add("normal", [image(5)])
        calls = []

        def encode(frames):
            calls.append(len(frames))
            return np.ones(4, np.float32)

        self.service.embedding(info["id"], "enc_a", encode)
        self.service.embedding(info["id"], "enc_a", encode)
        self.service.embedding(info["id"], "enc_b", encode)
        self.assertEqual(calls, [1, 1])  # enc_a 第二次讀快取
        bank = self.service.build_bank("enc_a", encode)
        self.assertEqual(bank["normal"][1].shape, (1, 4))
        self.assertEqual(bank["collision"][0], [])
        self.assertEqual(self.service.clear_embedding_cache(), 2)


if __name__ == "__main__":
    unittest.main()
