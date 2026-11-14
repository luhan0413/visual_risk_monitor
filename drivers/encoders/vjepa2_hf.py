"""
V-JEPA 2 encoder（Hugging Face transformers 格式，從本機 models/ 資料夾載入）。

輸入一段影格，輸出 encoder 最後一層 token 的平均（ViT-L 為 1024 維）。
只讀取 model_path，不會連網下載；權重請放在 models/<名稱>/：
    config.json、model.safetensors、video_preprocessor_config.json
沒有權重時執行 scripts/download_model.py。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np

from core.interfaces import EncoderDriver

_DTYPES = {"float32", "float16", "bfloat16"}
_REQUIRED_FILES = ("config.json", "model.safetensors", "video_preprocessor_config.json")


class VJEPA2HFEncoder(EncoderDriver):
    TUBELET = 2  # V-JEPA 2 每 2 張影格合成一個時間 token，影格數需為偶數

    def __init__(self, model_path: str, device: str = "cuda", dtype: str = "float16"):
        if dtype not in _DTYPES:
            raise ValueError(f"dtype must be one of {sorted(_DTYPES)}")
        self.model_path = Path(model_path)
        self.device_name = device
        self.dtype_name = dtype
        self._model = None
        self._processor = None
        self._device = None
        self._lock = threading.Lock()

    def _check_files(self) -> None:
        missing = [name for name in _REQUIRED_FILES if not (self.model_path / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"模型權重不完整：{self.model_path} 缺少 {', '.join(missing)}。"
                f"請執行 scripts/download_model.py"
            )

    def load(self) -> None:
        import torch
        from transformers import AutoModel, AutoVideoProcessor

        self._check_files()
        device = self.device_name
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("設定為 cuda，但目前無法使用 CUDA")
        dtype = getattr(torch, self.dtype_name)
        if device == "cpu" and dtype is torch.float16:
            dtype = torch.float32

        processor = AutoVideoProcessor.from_pretrained(self.model_path, local_files_only=True)
        model = AutoModel.from_pretrained(self.model_path, dtype=dtype, local_files_only=True)
        model.to(device).eval()

        with self._lock:
            self._processor = processor
            self._model = model
            self._device = torch.device(device)

    def unload(self) -> None:
        with self._lock:
            self._model = None
            self._processor = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def _prepare(self, frames: list[np.ndarray]) -> np.ndarray:
        if not frames:
            raise ValueError("frames must not be empty")
        frames = list(frames)
        # 單張圖片或奇數張時，重複最後一張補到偶數
        while len(frames) < self.TUBELET or len(frames) % self.TUBELET:
            frames.append(frames[-1])
        return np.stack(frames)  # (T, H, W, 3)

    def encode(self, frames: list[np.ndarray]) -> np.ndarray:
        import torch

        with self._lock:
            if self._model is None:
                raise RuntimeError("模型尚未載入")
            video = torch.from_numpy(self._prepare(frames)).permute(0, 3, 1, 2)  # T, C, H, W
            inputs = self._processor(video, return_tensors="pt")
            pixels = inputs["pixel_values_videos"].to(self._device, dtype=self._model.dtype)
            with torch.inference_mode():
                tokens = self._model.get_vision_features(pixel_values_videos=pixels)
            vector = tokens.float().mean(dim=1)[0]
            return vector.cpu().numpy().astype(np.float32)

    def info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "model_path": str(self.model_path),
            "device": self.device_name,
            "dtype": self.dtype_name,
        }
        if self._model is not None:
            info["dim"] = int(self._model.config.hidden_size)
        return info
