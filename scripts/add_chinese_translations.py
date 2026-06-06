#!/usr/bin/env python3
"""Add Chinese translations to the static paper data bundle.

The script keeps a local cache so reruns only translate missing strings.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from deep_translator import GoogleTranslator


ROOT = Path(__file__).resolve().parents[1]
PAPERS_JSON = ROOT / "data" / "papers.json"
SUMMARY_JSON = ROOT / "data" / "summary.json"
CACHE_JSON = ROOT / "data" / "translation_cache.json"


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


def split_for_translation(text: str, limit: int = 4200) -> list[str]:
    text = normalize(text)
    if len(text) <= limit:
        return [text]
    sentences = []
    current = []
    current_len = 0
    for part in text.replace(". ", ".\n").splitlines():
        part = part.strip()
        if not part:
            continue
        if current_len + len(part) + 1 > limit and current:
            sentences.append(" ".join(current))
            current = [part]
            current_len = len(part)
        else:
            current.append(part)
            current_len += len(part) + 1
    if current:
        sentences.append(" ".join(current))
    return sentences


def translate_text(text: str, translator: GoogleTranslator, cache: dict[str, str]) -> str:
    text = normalize(text)
    if not text:
        return ""
    key = cache_key(text)
    if key in cache:
        return cache[key]

    if len(text) > 4200:
        chunks = split_for_translation(text)
        translated_chunks = [translate_text(chunk, translator, cache) for chunk in chunks]
        translated = normalize(" ".join(chunk for chunk in translated_chunks if chunk))
        cache[key] = translated
        return translated

    for attempt in range(4):
        try:
            translated = normalize(translator.translate(text))
            if translated:
                cache[key] = translated
                return translated
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    cache[key] = ""
    return ""


def translate_many(texts: list[str], translator: GoogleTranslator, cache: dict[str, str]) -> list[str]:
    normalized_texts = [normalize(text) for text in texts]
    results = [""] * len(normalized_texts)
    missing_positions = []
    missing_texts = []

    for index, text in enumerate(normalized_texts):
        if not text:
            continue
        key = cache_key(text)
        if key in cache:
            results[index] = cache[key]
        elif len(text) > 4200:
            results[index] = translate_text(text, translator, cache)
        else:
            missing_positions.append(index)
            missing_texts.append(text)

    if missing_texts:
        try:
            batch_results = translator.translate_batch(missing_texts)
            for position, source, translated in zip(missing_positions, missing_texts, batch_results):
                translated = normalize(translated)
                cache[cache_key(source)] = translated
                results[position] = translated
        except Exception:
            for position, source in zip(missing_positions, missing_texts):
                results[position] = translate_text(source, translator, cache)
    return results


def main() -> None:
    data = json.loads(PAPERS_JSON.read_text(encoding="utf-8"))
    cache = load_cache()
    translator = GoogleTranslator(source="en", target="zh-CN")

    papers = data.get("papers", [])
    total = len(papers)
    translated = 0
    missing = 0

    for start in range(0, total, 10):
        batch = papers[start:start + 10]
        title_results = translate_many([paper.get("title", "") for paper in batch], translator, cache)
        abstract_results = translate_many([paper.get("abstract", "") for paper in batch], translator, cache)

        for offset, paper in enumerate(batch):
            paper["title_zh"] = title_results[offset]
            paper["abstract_zh"] = abstract_results[offset]
            abstract = normalize(paper.get("abstract", ""))
            if paper["title_zh"] and (paper["abstract_zh"] or not abstract):
                translated += 1
            else:
                missing += 1

        index = min(start + len(batch), total)
        save_cache(cache)
        print(f"{index}/{total} translated={translated} missing={missing}", flush=True)
        time.sleep(0.35)

    # Keep the old loop counters out of the final accounting.
    translated = 0
    missing = 0
    for paper in papers:
        abstract = normalize(paper.get("abstract", ""))
        if paper["title_zh"] and (paper["abstract_zh"] or not abstract):
            translated += 1
        else:
            missing += 1

    save_cache(cache)

    summary = data.setdefault("summary", {})
    summary["translation"] = {
        "target": "zh-CN",
        "engine": "GoogleTranslator via deep-translator",
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
