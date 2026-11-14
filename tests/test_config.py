"""
config.py 只放值、config_service 負責計算的測試。
"""
import ast
import unittest
from pathlib import Path

from services import config_service as cfg

CONFIG_FILE = Path(__file__).resolve().parents[1] / "config.py"


class ConfigTest(unittest.TestCase):
    def test_config_has_only_literal_values(self):
        """config.py 每一個設定都必須是純值（不能有運算、函式呼叫、引用其他變數、f-string）。"""
        tree = ast.parse(CONFIG_FILE.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue  # 檔案說明
            self.assertIsInstance(node, ast.Assign, f"config.py 第 {node.lineno} 行不是設定值")
            try:
                ast.literal_eval(node.value)
            except ValueError:
                self.fail(f"config.py 第 {node.lineno} 行含有計算，請改成純值，計算放到 services/config_service.py")

    def test_validate_default_config(self):
        self.assertEqual(cfg.validate(), [])

    def test_relative_paths_resolve_to_project_root(self):
        self.assertEqual(cfg.path("exemplars"), cfg.PROJECT_ROOT / "data" / "exemplars")
        self.assertTrue(cfg.resolve_path("/abs/dir").is_absolute())
        _, kwargs = cfg.source_driver("replay")
        self.assertEqual(Path(kwargs["video_dir"]), cfg.PROJECT_ROOT / "data" / "videos")

    def test_url_source_uses_stream_driver_with_defaults(self):
        driver, kwargs = cfg.source_driver("left_wrist")
        self.assertEqual(driver, "http_stream")
        self.assertIn("url", kwargs)
        self.assertIn("reconnect_s", kwargs)

    def test_snapshot_url_is_not_passed_to_stream_driver(self):
        _, kwargs = cfg.source_driver("left_wrist")
        self.assertNotIn("snapshot_url", kwargs)
        self.assertTrue(cfg.snapshot_url("left_wrist").startswith("http"))
        self.assertIsNone(cfg.snapshot_url("replay"))
        self.assertIsNone(cfg.snapshot_url(None))
        cfg.make_source("left_wrist")  # 建立 driver 不會因為多餘參數失敗（不會連線）

    def test_scorer_kwargs_from_config(self):
        scorer = cfg.make_scorer("knn")
        self.assertEqual(scorer.k, cfg.get("SCORERS")["knn"]["kwargs"]["k"])


if __name__ == "__main__":
    unittest.main()
