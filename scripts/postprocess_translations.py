#!/usr/bin/env python3
"""Fix common machine-translation terminology errors in paper translations."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAPERS_JSON = ROOT / "data" / "papers.json"
SUMMARY_JSON = ROOT / "data" / "summary.json"

REPLACEMENTS = [
    ("教育部", "MoE"),
    ("混合专家", "专家混合"),
    ("专家的混合", "专家混合"),
    ("愿景", "视觉"),
    ("变异器", "Transformer"),
    ("视觉变换器", "Vision Transformer"),
    ("图像标记", "图像 token"),
    ("文字标记", "文本 token"),
    ("代币", "token"),
    ("查询", "Query"),
    ("关键、价值", "Key、Value"),
    ("钥匙、价值", "Key、Value"),
    ("交叉注意力力", "交叉注意力"),
    ("交叉努力", "交叉注意力"),
    ("交叉注意", "交叉注意力"),
    ("交叉注意力力", "交叉注意力"),
    ("自我注意", "自注意力"),
    ("地物", "特征"),
    ("装配的表示方式", "融合表示"),
    ("脱钩", "解耦"),
    ("扭曲", "失真"),
    ("视觉经验", "视觉体验"),
    ("最新业绩", "SOTA 性能"),
    ("质量层面", "质量维度"),
    ("倒数第二的特征", "倒数第二层特征"),
    ("建议通过", "提出通过"),
    ("本文调查", "本文研究"),
    ("GCN强化", "GCN 增强"),
    ("层互动", "层交互"),
    ("特征互动", "特征交互"),
    ("提议以", "提出以"),
    ("有效质量", "有效的质量"),
    ("盲人图像质量", "盲图像质量"),
    ("生命-IQA", "Life-IQA"),
    ("本文件", "本文"),
    ("香草Transformer解码器", "vanilla Transformer decoder"),
    ("香草 Transformer 解码器", "vanilla Transformer decoder"),
    ("《BIQA》", "BIQA"),
    ("《IQA》", "IQA"),
]


def fix(text: str) -> str:
    text = str(text or "")
    for src, dst in REPLACEMENTS:
        text = text.replace(src, dst)
    return text


def main() -> None:
    data = json.loads(PAPERS_JSON.read_text(encoding="utf-8"))
    changed = 0
    for paper in data.get("papers", []):
        for key in ("title_zh", "abstract_zh"):
            old = paper.get(key, "")
            new = fix(old)
            if new != old:
                paper[key] = new
                changed += 1
    data.setdefault("summary", {}).setdefault("translation", {})["postprocess"] = {
        "term_replacements": len(REPLACEMENTS),
        "changed_fields": changed,
    }
    PAPERS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if SUMMARY_JSON.exists():
        summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    else:
        summary = {}
    summary.update(data.get("summary", {}))
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"postprocessed changed_fields={changed}")


if __name__ == "__main__":
    main()
