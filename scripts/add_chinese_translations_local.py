#!/usr/bin/env python3
"""Add Chinese translations with a local HuggingFace translation model."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import torch
from transformers import pipeline


ROOT = Path(__file__).resolve().parents[1]
PAPERS_JSON = ROOT / "data" / "papers.json"
SUMMARY_JSON = ROOT / "data" / "summary.json"
CACHE_JSON = ROOT / "data" / "translation_cache.json"
MODEL_NAME = "Helsinki-NLP/opus-mt-en-zh"


def normalize(text: str) -> str:
    return " ".join(str(text or "").split())


def cache_key(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def load_cache() -> dict[str, str]:
    if not CACHE_JSON.exists():
        return {}
    return json.loads(CACHE_JSON.read_text(encoding="utf-8"))


def save_cache(cache: dict[str, str]) -> None:
    CACHE_JSON.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def split_text(text: str, limit: int = 320) -> list[str]:
    text = normalize(text)
    if len(text) <= limit:
        return [text]
    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = []
    current_len = 0
    for part in parts:
        if not part:
            continue
        if current and current_len + len(part) + 1 > limit:
            chunks.append(" ".join(current))
            current = [part]
            current_len = len(part)
        else:
            current.append(part)
            current_len += len(part) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def translate_uncached(texts: list[str], translator) -> list[str]:
    outputs = translator(
        texts,
        batch_size=8,
        max_length=512,
        truncation=True,
    )
    return [normalize(item["translation_text"]) for item in outputs]


def translate_text(text: str, translator, cache: dict[str, str]) -> str:
    text = normalize(text)
    if not text:
        return ""
    key = cache_key(text)
    if key in cache:
        return cache[key]

    chunks = split_text(text)
    translated_chunks = []
    for start in range(0, len(chunks), 8):
        translated_chunks.extend(translate_uncached(chunks[start:start + 8], translator))
    translated = normalize(" ".join(translated_chunks))
    cache[key] = translated
    return translated


def main() -> None:
    data = json.loads(PAPERS_JSON.read_text(encoding="utf-8"))
    papers = data.get("papers", [])
    cache = load_cache()
    device = 0 if torch.cuda.is_available() else -1
    translator = pipeline("translation", model=MODEL_NAME, device=device)

    total = len(papers)
    translated = 0
    missing = 0
    for index, paper in enumerate(papers, start=1):
        paper["title_zh"] = translate_text(paper.get("title", ""), translator, cache)
        paper["abstract_zh"] = translate_text(paper.get("abstract", ""), translator, cache)
        abstract = normalize(paper.get("abstract", ""))
        if paper["title_zh"] and (paper["abstract_zh"] or not abstract):
            translated += 1
        else:
            missing += 1

        if index % 25 == 0:
            save_cache(cache)
            print(f"{index}/{total} translated={translated} missing={missing}", flush=True)

    save_cache(cache)
    summary = data.setdefault("summary", {})
    summary["translation"] = {
        "target": "zh-CN",
        "engine": MODEL_NAME,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "translated_papers": translated,
        "missing_translation_papers": missing,
    }
    PAPERS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if SUMMARY_JSON.exists():
        summary_data = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    else:
        summary_data = {}
    summary_data.update(summary)
    SUMMARY_JSON.write_text(json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done translated={translated} missing={missing} cache={len(cache)}")


if __name__ == "__main__":
    main()
