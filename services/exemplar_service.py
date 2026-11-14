"""
範例庫服務。

磁碟結構（每個範例一個資料夾，存原始影格，所以換模型時可以重新計算特徵）：

    data/exemplars/<label>/<exemplar_id>/
        frames/000.jpg, 001.jpg, ...
        thumb.jpg                    縮圖（最後一張影格）
        meta.json                    來源、時間等資訊
        emb_<encoder_name>.npy       特徵快取（依模型分開存）
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

_ID_PATTERN = re.compile(r"^[a-z0-9_]+-\d{8}-\d{6}-[0-9a-f]{6}$")
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class ExemplarService:
    def __init__(
        self,
        root: Path,
        labels: tuple[str, ...] | list[str],
        frame_jpeg_quality: int = 95,
        thumbnail_size: int = 240,
        thumbnail_jpeg_quality: int = 85,
    ):
        self.root = Path(root)
        self.frame_jpeg_quality = int(frame_jpeg_quality)
        self.thumbnail_size = int(thumbnail_size)
        self.thumbnail_jpeg_quality = int(thumbnail_jpeg_quality)
        self.labels = tuple(labels)
        for label in self.labels:
            if not re.fullmatch(r"[a-z0-9_]+", label):
                raise ValueError(f"label 只能使用小寫英數與底線：{label}")
            (self.root / label).mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.version = 0  # 新增 / 刪除時 +1

    # ---------- helpers ----------

    def check_label(self, label: str) -> str:
        if label not in self.labels:
            raise ValueError(f"不支援的類別：{label}（可用：{', '.join(self.labels)}）")
        return label

    def _path(self, exemplar_id: str) -> Path:
        if not isinstance(exemplar_id, str) or not _ID_PATTERN.fullmatch(exemplar_id):
            raise ValueError(f"無效的範例 ID：{exemplar_id}")
        label = exemplar_id.rsplit("-", 3)[0]
        self.check_label(label)
        path = self.root / label / exemplar_id
        if not path.is_dir():
            raise FileNotFoundError(f"找不到範例：{exemplar_id}")
        return path

    @staticmethod
    def _read_meta(path: Path) -> dict[str, Any]:
        try:
            return json.loads((path / "meta.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"id": path.name, "label": path.parent.name}

    # ---------- write ----------

    def add(self, label: str, frames: list[np.ndarray], meta: dict[str, Any] | None = None) -> dict[str, Any]:
        """frames: RGB 影像（一張圖片或一段影格）。"""
        self.check_label(label)
        if not frames:
            raise ValueError("frames must not be empty")
        exemplar_id = f"{label}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        path = self.root / label / exemplar_id
        (path / "frames").mkdir(parents=True)
        try:
            for index, image in enumerate(frames):
                bgr = cv2.cvtColor(np.asarray(image, dtype=np.uint8), cv2.COLOR_RGB2BGR)
                if not cv2.imwrite(str(path / "frames" / f"{index:03d}.jpg"), bgr, [cv2.IMWRITE_JPEG_QUALITY, self.frame_jpeg_quality]):
                    raise RuntimeError("影像寫入失敗")
            thumb = cv2.cvtColor(np.asarray(frames[-1], dtype=np.uint8), cv2.COLOR_RGB2BGR)
            height, width = thumb.shape[:2]
            scale = self.thumbnail_size / max(height, width)
            if scale < 1:
                thumb = cv2.resize(thumb, (int(width * scale), int(height * scale)))
            cv2.imwrite(str(path / "thumb.jpg"), thumb, [cv2.IMWRITE_JPEG_QUALITY, self.thumbnail_jpeg_quality])
            info = {
                "id": exemplar_id,
                "label": label,
                "created_at": time.time(),
                "frame_count": len(frames),
                **(meta or {}),
            }
            (path / "meta.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            shutil.rmtree(path, ignore_errors=True)
            raise
        with self._lock:
            self.version += 1
        return info

    def delete(self, exemplar_id: str) -> None:
        path = self._path(exemplar_id)
        shutil.rmtree(path)
        with self._lock:
            self.version += 1

    # ---------- read ----------

    def list(self, label: str | None = None) -> list[dict[str, Any]]:
        labels = [self.check_label(label)] if label else self.labels
        items = []
        for name in labels:
            for path in sorted((self.root / name).iterdir()):
                if path.is_dir() and _ID_PATTERN.fullmatch(path.name):
                    items.append(self._read_meta(path))
        return sorted(items, key=lambda item: item.get("created_at", 0), reverse=True)

    def ids(self, label: str) -> list[str]:
        folder = self.root / self.check_label(label)
        return sorted(p.name for p in folder.iterdir() if p.is_dir() and _ID_PATTERN.fullmatch(p.name))

    def summary(self, label: str | None = None) -> dict[str, Any]:
        return {"labels": list(self.labels), "counts": self.counts(), "items": self.list(label or None)}

    def counts(self) -> dict[str, int]:
        return {label: len(self.ids(label)) for label in self.labels}

    def thumbnail_path(self, exemplar_id: str) -> Path:
        return self._path(exemplar_id) / "thumb.jpg"

    def load_frames(self, exemplar_id: str) -> list[np.ndarray]:
        frames = []
        for file in sorted((self._path(exemplar_id) / "frames").glob("*.jpg")):
            image = cv2.imread(str(file), cv2.IMREAD_COLOR)
            if image is not None:
                frames.append(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        if not frames:
            raise RuntimeError(f"範例沒有影格：{exemplar_id}")
        return frames

    # ---------- embeddings ----------

    def embedding(self, exemplar_id: str, encoder_name: str, encode: Callable[[list[np.ndarray]], np.ndarray]) -> np.ndarray:
        if not _NAME_PATTERN.fullmatch(encoder_name):
            raise ValueError(f"無效的 encoder 名稱：{encoder_name}")
        cache = self._path(exemplar_id) / f"emb_{encoder_name}.npy"
        if cache.exists():
            return np.load(cache)
        vector = np.asarray(encode(self.load_frames(exemplar_id)), dtype=np.float32)
        np.save(cache, vector)
        return vector

    def clear_embedding_cache(self, encoder_name: str | None = None) -> int:
        pattern = f"emb_{encoder_name}.npy" if encoder_name else "emb_*.npy"
        removed = 0
        for file in self.root.glob(f"*/*/{pattern}"):
            file.unlink()
            removed += 1
        return removed

    def build_bank(self, encoder_name: str, encode: Callable) -> dict[str, tuple[list[str], np.ndarray]]:
        bank = {}
        for label in self.labels:
            ids = self.ids(label)
            vectors = [self.embedding(exemplar_id, encoder_name, encode) for exemplar_id in ids]
            matrix = np.stack(vectors) if vectors else np.zeros((0, 0), dtype=np.float32)
            bank[label] = (ids, matrix)
        return bank
