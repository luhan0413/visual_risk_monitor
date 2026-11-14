"""Model Server 的服務層：模型載入狀態、模型清單、影像解碼與特徵計算。"""
from __future__ import annotations

from typing import Any

from services import config_service as cfg
from services.encoder_service import EncoderService
from services.image_codec import decode_images


def gpu_info() -> dict[str, Any]:
    try:
        import torch

        if torch.cuda.is_available():
            return {"cuda": True, "device": torch.cuda.get_device_name(0)}
        return {"cuda": False}
    except ImportError:
        return {"cuda": False, "torch": "not installed"}


class ModelServerService:
    def __init__(self, encoders: EncoderService, max_frames: int):
        self.encoders = encoders
        self.max_frames = int(max_frames)

    def status(self) -> dict[str, Any]:
        return {"model": self.encoders.status(), "models_dir": str(cfg.path("models")), "gpu": gpu_info()}

    def models(self) -> list[dict[str, Any]]:
        return cfg.server_models()

    def load(self, model_name: str) -> dict[str, Any]:
        return self.encoders.select(model_name, background=True)

    def unload(self) -> dict[str, Any]:
        return self.encoders.unload()

    def encode(self, files: list[tuple[str, bytes]], model_name: str | None = None) -> dict[str, Any]:
        """files: [(檔名, JPEG bytes), ...]，依時間排序。"""
        if model_name and model_name != self.encoders.name:
            raise RuntimeError(f"目前載入的模型是 {self.encoders.name}，不是 {model_name}")
        frames = decode_images(files, max_count=self.max_frames)
        vector = self.encoders.encode(frames)
        return {
            "model_name": self.encoders.name,
            "embedding": vector.tolist(),
            "dim": int(vector.shape[0]),
            "frames": len(frames),
            "latency_ms": self.encoders.status()["last_latency_ms"],
        }


def build_service() -> ModelServerService:
    settings = cfg.get("MODEL_SERVER")
    return ModelServerService(
        EncoderService(factory=cfg.make_server_encoder),
        max_frames=settings["max_frames_per_request"],
    )
