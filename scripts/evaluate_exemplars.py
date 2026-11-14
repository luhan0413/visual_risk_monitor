"""
離線評估範例庫（留一法 leave-one-out）。

每個範例輪流當「測試」，其餘範例當範例庫，看它會被打幾分、分到哪一級。
用來判斷：這個模型 + 評分方法在你的場景能不能分辨正常與碰撞，門檻該設多少。

用法（在專案根目錄執行）：
    python scripts/evaluate_exemplars.py
    python scripts/evaluate_exemplars.py --encoder dummy --scorer centroid
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

import config  # noqa: E402
from core.risk import RiskLeveler  # noqa: E402
from drivers import loader  # noqa: E402
from services.encoder_service import EncoderService  # noqa: E402
from services.exemplar_service import ExemplarService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--encoder", default=config.DEFAULT_ENCODER, choices=list(config.ENCODERS))
    parser.add_argument("--scorer", default=config.DEFAULT_SCORER, choices=list(config.SCORERS))
    args = parser.parse_args()

    positive, negative = config.POSITIVE_LABEL, config.NEGATIVE_LABEL
    exemplars = ExemplarService(config.EXEMPLAR_DIR, config.EXEMPLAR_LABELS)
    counts = exemplars.counts()
    print(f"範例數：{counts}")
    if min(counts[positive], counts[negative]) < 2:
        print("每一類至少需要 2 個範例才能做留一法評估。")
        return 1

    encoders = EncoderService()
    print(f"載入模型 {args.encoder} …")
    encoders.select(args.encoder, background=False)
    if not encoders.ready:
        print(f"模型載入失敗：{encoders.status()['error']}")
        return 1

    bank = exemplars.build_bank(args.encoder, encoders.encode)
    leveler = RiskLeveler(config.RISK["levels"])
    rows = []  # (id, true_label, score)
    for label in (negative, positive):
        ids, matrix = bank[label]
        for i, exemplar_id in enumerate(ids):
            held_out = {
                lab: ([x for j, x in enumerate(lab_ids) if not (lab == label and j == i)],
                      np.delete(lab_matrix, i, axis=0) if lab == label else lab_matrix)
                for lab, (lab_ids, lab_matrix) in bank.items()
            }
            scorer = loader.create_scorer(args.scorer)
            scorer.fit(held_out, positive=positive, negative=negative)
            rows.append((exemplar_id, label, scorer.score(matrix[i]).score))

    print(f"\n{'範例':<40} {'實際':<10} {'分數':>6}  等級")
    for exemplar_id, label, score in rows:
        print(f"{exemplar_id:<40} {label:<10} {score:6.1f}  {leveler.classify(score)['name']}")

    pos_scores = np.array([s for _, lab, s in rows if lab == positive])
    neg_scores = np.array([s for _, lab, s in rows if lab == negative])
    print(f"\n{positive} 分數：平均 {pos_scores.mean():.1f}，最低 {pos_scores.min():.1f}")
    print(f"{negative} 分數：平均 {neg_scores.mean():.1f}，最高 {neg_scores.max():.1f}")

    print("\n各門檻的表現（分數 >= 門檻視為警示）：")
    print(f"{'門檻':>6} {'碰撞召回率':>10} {'正常誤報率':>10}")
    for threshold in sorted({level["min"] for level in config.RISK["levels"] if level["min"] > 0} | {50, 70}):
        recall = float(np.mean(pos_scores >= threshold))
        false_alarm = float(np.mean(neg_scores >= threshold))
        print(f"{threshold:>6} {recall:>10.0%} {false_alarm:>10.0%}")

    if pos_scores.min() > neg_scores.max():
        print(f"\n兩組完全分開：門檻設在 {neg_scores.max():.1f} ～ {pos_scores.min():.1f} 之間都能正確區分。")
    else:
        print("\n兩組有重疊：請檢查重疊的範例（標註是否正確、拍攝角度是否一致），或增加範例數。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
