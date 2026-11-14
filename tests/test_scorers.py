import unittest

import numpy as np

from drivers.scorers.centroid import CentroidScorer
from drivers.scorers.knn import KNNScorer


def make_bank(rng):
    normal = rng.normal(0, 0.1, (5, 8)) + np.eye(8)[0]
    collision = rng.normal(0, 0.1, (5, 8)) + np.eye(8)[1]
    return {
        "normal": ([f"normal-{i}" for i in range(5)], normal.astype(np.float32)),
        "collision": ([f"collision-{i}" for i in range(5)], collision.astype(np.float32)),
    }


class ScorerTest(unittest.TestCase):
    def check(self, scorer):
        rng = np.random.default_rng(0)
        self.assertFalse(scorer.score(np.ones(8, np.float32)).ready)
        scorer.fit(make_bank(rng), positive="collision", negative="normal")

        near_collision = scorer.score(np.eye(8, dtype=np.float32)[1])
        near_normal = scorer.score(np.eye(8, dtype=np.float32)[0])
        self.assertTrue(near_collision.ready)
        self.assertGreater(near_collision.score, 85)
        self.assertLess(near_normal.score, 15)
        self.assertEqual(near_collision.nearest["label"], "collision")
        self.assertEqual(near_normal.nearest["label"], "normal")
        self.assertTrue(0 <= near_collision.score <= 100)

    def test_knn(self):
        self.check(KNNScorer(k=3))

    def test_centroid(self):
        self.check(CentroidScorer())

    def test_missing_label_rejected(self):
        bank = make_bank(np.random.default_rng(1))
        bank["collision"] = ([], np.zeros((0, 8), np.float32))
        with self.assertRaises(ValueError):
            KNNScorer().fit(bank, positive="collision", negative="normal")


if __name__ == "__main__":
    unittest.main()
