"""
下載 Hugging Face 上的模型權重到 models/<名稱>/。

用法（在專案根目錄執行）：
    python scripts/download_model.py                                   # 預設 V-JEPA 2 ViT-L
    python scripts/download_model.py --repo facebook/vjepa2-vitg-fpc64-384

下載後，在 config.MODEL_SERVER_MODELS 新增一筆指向該資料夾即可使用。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402

FILES = ["config.json", "model.safetensors", "video_preprocessor_config.json"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default="facebook/vjepa2-vitl-fpc64-256", help="Hugging Face repo id")
    parser.add_argument("--name", help="models/ 底下的資料夾名稱（預設為 repo 名稱）")
    args = parser.parse_args()

    from huggingface_hub import snapshot_download

    target = config.MODEL_DIR / (args.name or args.repo.split("/")[-1])
    print(f"下載 {args.repo} → {target}")
    snapshot_download(repo_id=args.repo, local_dir=target, allow_patterns=FILES)
    missing = [name for name in FILES if not (target / name).is_file()]
    if missing:
        print(f"缺少檔案：{', '.join(missing)}")
        return 1
    print("完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
