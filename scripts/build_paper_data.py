#!/usr/bin/env python3
"""Build the static data bundle for the Vision MoE Paper Atlas."""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import math
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CLIP_ROOT = ROOT.parent
CVPAPER_ROOT = CLIP_ROOT / "reference_repos" / "CVpaper"
MAIN_CSV = CVPAPER_ROOT / "cv_paper.csv"
HTML_DIR = CVPAPER_ROOT / "html"
OUT_JSON = ROOT / "data" / "papers.json"
OUT_SUMMARY = ROOT / "data" / "summary.json"
CVPR2026_JSONL = CLIP_ROOT / "MoE-PCQA" / "external" / "cvpr2026_moe" / "cvpr_papers.jsonl"

STRICT_PATTERNS = [
    r"\bmoe\b",
    r"\bmixture[- ]of[- ]experts?\b",
    r"\bmixtures[- ]of[- ]experts?\b",
    r"\bmixture[- ]of[- ]vision[- ]experts?\b",
    r"\bmixture[- ]of[- ]biometric[- ]experts?\b",
]

ADJACENT_PATTERNS = [
    r"\bexpert(?:s)?\b",
    r"\brouter(?:s)?\b",
    r"\brouting\b",
    r"\bgating\b",
    r"\bgated\b",
    r"\bconditional routing\b",
    r"\bdynamic routing\b",
    r"\bsparse routing\b",
    r"\bexpert choice\b",
    r"\btoken choice\b",
]

VISION_TERMS = {
    "vision", "visual", "image", "images", "video", "videos", "object", "scene",
    "segmentation", "detection", "recognition", "tracking", "camera", "3d",
    "point", "cloud", "multimodal", "multimodal", "rgb", "depth", "restoration",
    "quality", "clip", "vit", "transformer", "biometric", "face", "pose",
    "classification", "generation", "diffusion", "editing", "medical", "remote",
}

NON_CV_TERMS = {
    "language model", "large language", "llm", "nlp", "machine translation",
    "speech recognition", "text generation", "code generation", "reasoning benchmark",
    "chatbot", "dialogue system",
}

STRONG_CV_TERMS = {
    "computer vision", "vision", "visual", "image", "images", "video", "videos",
    "object detection", "segmentation", "recognition", "tracking", "scene",
    "camera", "3d", "point cloud", "rgb", "depth", "restoration", "iqa",
    "quality assessment", "clip", "vit", "vision transformer", "face", "pose",
    "remote sensing", "medical image", "medical imaging", "multimodal",
    "vision-language", "visual-language", "low-level vision",
}

ALLOWED_EXTERNAL_VENUE_TERMS = {
    "computer vision", "pattern recognition", "image", "imaging", "visual",
    "video", "multimedia", "vision", "remote sensing", "medical image",
    "medical imaging", "wacv", "icme", "bmvc", "accv", "aaai", "neurips",
    "arxiv", "cvpr", "iccv", "eccv", "tpami", "ijcv", "tip", "tmm",
    "tcsvt", "transactions on visualization", "medical image analysis",
    "neurocomputing", "ieee access",
}

VISUAL_EVIDENCE_TERMS = {
    "computer vision", "image", "images", "visual", "vision", "video", "videos",
    "point cloud", "point-cloud", "lidar", "3d", "rgb", "depth", "segmentation",
    "detection", "recognition", "tracking", "restoration", "deblurring",
    "denoising", "super-resolution", "saliency", "captioning",
    "visual question answering", "video question answering", "retrieval",
    "re-identification", "reid", "object", "scene", "camera", "medical image",
    "medical imaging", "histopathology", "mammogram", "retinal", "oct", "mri",
    "ct", "remote sensing", "light field", "clip", "vlm", "vision-language",
    "visual-language", "vit", "vision transformer", "driver state", "panoramic",
    "biometric", "face", "pose",
}

GENERIC_EXTERNAL_TERMS = {
    "large language model", "large language models", "llm", "llms",
    "natural language", "named entity", "speech", "translation", "database",
    "petroleum", "digital rock", "recommender system",
}

GENERIC_EXTERNAL_TITLE_PATTERNS = [
    r"\ba survey on mixture of experts\b",
    r"\bsurvey on mixture[- ]of[- ]experts\b",
    r"\bthe evolution of mixture of experts\b",
    r"\ba review of sparse expert models\b",
    r"\bmoe at scale\b",
    r"\btutel\b",
    r"\bflexmoe\b",
    r"\brecommend(?:ing|ation|er)\b",
    r"\bfederated learning\b",
    r"\baddressing confounding feature issue\b",
    r"\bmodeling task relationships\b",
]

TITLE_CV_ALLOW_TERMS = {
    "vision", "visual", "image", "video", "point cloud", "point-cloud", "lidar",
    "3d", "medical", "mammogram", "histopathology", "retinal", "remote sensing",
    "segmentation", "detection", "recognition", "tracking", "deblurring",
    "denoising", "super-resolution", "captioning", "retrieval", "reid",
    "re-identification", "object", "face", "pose", "light field", "clip", "vlm",
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "into", "is",
    "it", "of", "on", "or", "over", "the", "to", "towards", "toward", "via", "with",
    "without", "using", "learning", "network", "networks", "model", "models", "method",
    "methods", "paper", "cvpr", "iccv", "eccv", "wacv", "2020", "2021", "2022",
    "2023", "2024", "2025", "2026",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clean_text(text: str) -> str:
    text = html.unescape(str(text or "")).replace("\u00a0", " ")
    text = re.sub(r"\\underline\s*([A-Za-z])\s+([A-Za-z]+)", r"\1\2", text)
    text = re.sub(r"\\(?:textbf|textit|emph|texttt|mathbf)\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:cite|coloredcite|ref|label|href)\s*\{[^{}]*\}", " ", text)
    text = text.replace("\\", " ")
    return normalize_space(text)


def tokenize(text: str) -> list[str]:
    text = clean_text(text).lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


STRICT_RE = compile_patterns(STRICT_PATTERNS)
ADJACENT_RE = compile_patterns(ADJACENT_PATTERNS)


def find_matches(text: str) -> tuple[list[str], list[str]]:
    strict = sorted({p.pattern.strip("\\b").replace("\\", "") for p in STRICT_RE if p.search(text)})
    adjacent = sorted({p.pattern.strip("\\b").replace("\\", "") for p in ADJACENT_RE if p.search(text)})
    return strict, adjacent


def classify_relevance(title: str, abstract: str) -> tuple[str | None, list[str]]:
    text = f"{title}\n{abstract}"
    strict, adjacent = find_matches(text)
    if strict:
        return "strict_moe", strict
    if adjacent:
        return "adjacent_expert_routing", adjacent
    return None, []


def parse_author_field(authors: str) -> tuple[str, str, str]:
    authors = clean_text(authors)
    venue = ""
    year = ""
    cleaned_authors = authors

    year_match = re.search(r"\b(20(?:1[3-9]|2[0-6]))\b", authors)
    if year_match:
        year = year_match.group(1)

    if re.search(r"\bCVPR\b|Computer Vision and Pattern Recognition", authors, re.I):
        venue = "CVPR"
    elif re.search(r"\bICCV\b|International Conference on Computer Vision", authors, re.I):
        venue = "ICCV"
    elif re.search(r"\bECCV\b|European Conference on Computer Vision", authors, re.I):
        venue = "ECCV"

    if ";" in authors:
        cleaned_authors = authors.split(";", 1)[0].strip()
    return cleaned_authors, venue, year


def url_tokens(url: str) -> set[str]:
    base = Path(urllib.parse.urlparse(url).path).name
    base = re.sub(r"(_paper|_Paper)?\.(html|php|pdf)$", "", base, flags=re.I)
    base = re.sub(r"\b(CVPR|ICCV|ECCV|WACV)\b", " ", base, flags=re.I)
    base = re.sub(r"\b20\d{2}\b", " ", base)
    return set(tokenize(base))


def load_link_records() -> list[dict]:
    records = []
    for venue, filename in [("CVPR", "cvpr.csv"), ("ICCV", "iccv.csv"), ("ECCV", "eccv.csv")]:
        path = HTML_DIR / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = clean_text(row.get("paper", ""))
                year = clean_text(row.get("year", ""))
                if not url:
                    continue
                records.append({
                    "venue": venue,
                    "year": year,
                    "url": url,
                    "tokens": url_tokens(url),
                })
    return records


def score_link(title_tokens: set[str], rec: dict) -> float:
    if not title_tokens or not rec["tokens"]:
        return 0.0
    overlap = len(title_tokens & rec["tokens"])
    if overlap == 0:
        return 0.0
    return overlap / math.sqrt(len(title_tokens) * len(rec["tokens"]))


def best_link_for(title: str, venue_hint: str, year_hint: str, link_records: list[dict]) -> dict | None:
    title_tokens = set(tokenize(title))
    if not title_tokens:
        return None

    candidates = link_records
    if venue_hint:
        candidates = [r for r in candidates if r["venue"] == venue_hint]
    if year_hint:
        year_candidates = [r for r in candidates if r["year"] == year_hint]
        if year_candidates:
            candidates = year_candidates

    best = None
    best_score = 0.0
    for rec in candidates:
        score = score_link(title_tokens, rec)
        if score > best_score:
            best_score = score
            best = rec
    if best and best_score >= 0.50:
        result = dict(best)
        result.pop("tokens", None)
        result["score"] = round(best_score, 3)
        return result
    return None


def scholar_url(title: str) -> str:
    return "https://scholar.google.com/scholar?q=" + urllib.parse.quote(title)


def cv_domain_score(title: str, abstract: str) -> int:
    text = f"{title} {abstract}".lower()
    return sum(1 for term in VISION_TERMS if term in text)


def strong_cv_domain_score(title: str, abstract: str) -> int:
    text = f"{title} {abstract}".lower()
    return sum(1 for term in STRONG_CV_TERMS if term in text)


def external_venue_allowed(venue: str) -> bool:
    text = venue.lower()
    return any(term in text for term in ALLOWED_EXTERNAL_VENUE_TERMS)


def visual_evidence_score(title: str, abstract: str) -> int:
    text = f"{title} {abstract}".lower()
    return sum(1 for term in VISUAL_EVIDENCE_TERMS if term in text)


def external_record_allowed(title: str, abstract: str, venue: str) -> bool:
    title_text = title.lower()
    text = f"{title} {abstract}".lower()
    evidence = visual_evidence_score(title, abstract)
    venue_is_cvish = external_venue_allowed(venue)

    if any(re.search(pattern, title_text) for pattern in GENERIC_EXTERNAL_TITLE_PATTERNS):
        return False
    if re.search(r"\blarge language models?\b|\bllms?\b", title_text):
        if "vision-language" not in title_text and "visual-language" not in title_text:
            return False
    if "survey" in title_text or "review" in title_text:
        if not any(term in title_text for term in TITLE_CV_ALLOW_TERMS):
            return False
    if any(term in text for term in GENERIC_EXTERNAL_TERMS) and evidence < 2:
        return False
    if evidence >= 2:
        return True
    if venue_is_cvish and evidence >= 1:
        return True
    return False


def looks_non_cv(title: str, abstract: str) -> bool:
    text = f"{title} {abstract}".lower()
    if any(term in text for term in NON_CV_TERMS) and cv_domain_score(title, abstract) < 2:
        return True
    return False


def build_from_cvpaper(link_records: list[dict]) -> list[dict]:
    df = pd.read_csv(MAIN_CSV)
    papers = []
    seen_titles = set()
    for idx, row in df.iterrows():
        title = clean_text(row.get("title", ""))
        abstract = clean_text(row.get("abstract", ""))
        authors_raw = clean_text(row.get("authors", ""))
        if not title or title.lower() in seen_titles:
            continue

        tier, tags = classify_relevance(title, abstract)
        if not tier:
            continue

        authors, venue, year = parse_author_field(authors_raw)
        link = best_link_for(title, venue, year, link_records)
        url = link["url"] if link else scholar_url(title)
        if link and not venue:
            venue = link["venue"]
        if link and not year:
            year = link["year"]

        papers.append({
            "id": f"cvpaper-{idx}",
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "venue": venue or "CVPR/ICCV/ECCV",
            "year": int(year) if year else 0,
            "url": url,
            "source": "choucisan/CVpaper",
            "tier": tier,
            "tags": tags,
            "link_confidence": link["score"] if link else 0.0,
            "cv_domain_score": cv_domain_score(title, abstract),
            "strong_cv_domain_score": strong_cv_domain_score(title, abstract),
            "visual_evidence_score": visual_evidence_score(title, abstract),
        })
        seen_titles.add(title.lower())
    return papers


def build_from_cvpr2026_jsonl(existing_titles: set[str]) -> list[dict]:
    if not CVPR2026_JSONL.exists():
        return []

    papers = []
    with CVPR2026_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            title = clean_text(row.get("title", ""))
            abstract = clean_text(row.get("abstract", ""))
            if not title or title.lower() in existing_titles:
                continue

            tier, tags = classify_relevance(title, abstract)
            if not tier and row.get("true_moe"):
                tier = "strict_moe"
                tags = ["true_moe"]
            if not tier:
                continue

            links = row.get("links") or []
            paper_url = next((url for url in links if "openaccess.thecvf.com" in url and "_paper.pdf" in url), "")
            url = paper_url or (links[0] if links else scholar_url(title))
            merged_tags = sorted(set(tags) | set(row.get("tags") or []))

            papers.append({
                "id": f"cvpr2026-{clean_text(row.get('paper_id', str(len(papers))))}",
                "title": title,
                "authors": clean_text(row.get("authors", "")),
                "abstract": abstract,
                "venue": "CVPR",
                "year": 2026,
                "url": url,
                "source": "CVPR2026 hongsong miner",
                "tier": tier,
                "tags": merged_tags,
                "link_confidence": 1.0 if paper_url else 0.7,
                "cv_domain_score": cv_domain_score(title, abstract),
                "strong_cv_domain_score": strong_cv_domain_score(title, abstract),
                "visual_evidence_score": visual_evidence_score(title, abstract),
                "paper_id": clean_text(row.get("paper_id", "")),
            })
            existing_titles.add(title.lower())
    return papers


def request_json(url: str, timeout: int = 20) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "moe-paper-atlas/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def request_text(url: str, timeout: int = 20) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "moe-paper-atlas/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def abstract_from_openalex(inv: dict | None) -> str:
    if not inv:
        return ""
    positions = []
    for token, locs in inv.items():
        for pos in locs:
            positions.append((pos, token))
    positions.sort()
    return clean_text(" ".join(token for _, token in positions))


def fetch_openalex_extras(existing_titles: set[str]) -> list[dict]:
    queries = [
        "computer vision mixture of experts",
        "vision mixture of experts routing",
        "image mixture of experts gating",
        "video mixture of experts",
        "visual expert routing",
        "multimodal vision experts routing",
        "point cloud mixture of experts",
    ]
    papers = []
    for query in queries:
        url = (
            "https://api.openalex.org/works?"
            + urllib.parse.urlencode({
                "search": query,
                "filter": "from_publication_date:2013-01-01",
                "per-page": "50",
            })
        )
        data = request_json(url)
        time.sleep(0.15)
        if not data:
            continue
        for item in data.get("results", []):
            title = clean_text(item.get("title", ""))
            if not title or title.lower() in existing_titles:
                continue
            abstract = abstract_from_openalex(item.get("abstract_inverted_index"))
            tier, tags = classify_relevance(title, abstract)
            if not tier or looks_non_cv(title, abstract):
                continue
            venue = clean_text(((item.get("primary_location") or {}).get("source") or {}).get("display_name") or "")
            # OpenAlex keyword search is broad. Keep it conservative so the
            # site remains a CV MoE atlas rather than a generic MoE database.
            if tier != "strict_moe":
                continue
            if not external_record_allowed(title, abstract, venue):
                continue
            year = item.get("publication_year") or 0
            url_value = clean_text(item.get("doi") or item.get("id") or scholar_url(title))
            if url_value.startswith("10."):
                url_value = "https://doi.org/" + url_value
            authors = ", ".join(
                clean_text(a.get("author", {}).get("display_name", ""))
                for a in item.get("authorships", [])[:12]
                if a.get("author")
            )
            papers.append({
                "id": f"openalex-{item.get('id', '').split('/')[-1]}",
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "venue": venue or "OpenAlex CV-related",
                "year": int(year) if year else 0,
                "url": url_value,
                "source": "OpenAlex search",
                "tier": tier,
                "tags": tags,
                "link_confidence": 1.0,
                "cv_domain_score": cv_domain_score(title, abstract),
                "strong_cv_domain_score": strong_cv_domain_score(title, abstract),
                "visual_evidence_score": visual_evidence_score(title, abstract),
            })
            existing_titles.add(title.lower())
    return papers


def fetch_arxiv_extras(existing_titles: set[str]) -> list[dict]:
    queries = [
        'cat:cs.CV AND all:"mixture of experts"',
        'cat:cs.CV AND all:"mixture-of-experts"',
        'cat:cs.CV AND all:"expert routing"',
        'cat:cs.CV AND all:"vision experts"',
        'cat:cs.CV AND all:"gating network"',
    ]
    ns = {"a": "http://www.w3.org/2005/Atom"}
    papers = []
    for query in queries:
        url = (
            "https://export.arxiv.org/api/query?"
            + urllib.parse.urlencode({
                "search_query": query,
                "start": "0",
                "max_results": "50",
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            })
        )
        text = request_text(url)
        time.sleep(0.25)
        if not text:
            continue
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            continue
        for entry in root.findall("a:entry", ns):
            title = clean_text(entry.findtext("a:title", default="", namespaces=ns))
            if not title or title.lower() in existing_titles:
                continue
            abstract = clean_text(entry.findtext("a:summary", default="", namespaces=ns))
            tier, tags = classify_relevance(title, abstract)
            if not tier or looks_non_cv(title, abstract):
                continue
            authors = ", ".join(clean_text(a.findtext("a:name", default="", namespaces=ns)) for a in entry.findall("a:author", ns))
            published = entry.findtext("a:published", default="", namespaces=ns)
            year = int(published[:4]) if published[:4].isdigit() else 0
            link = entry.findtext("a:id", default="", namespaces=ns)
            papers.append({
                "id": "arxiv-" + link.rsplit("/", 1)[-1].replace(".", "-"),
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "venue": "arXiv cs.CV",
                "year": year,
                "url": link or scholar_url(title),
                "source": "arXiv cs.CV search",
                "tier": tier,
                "tags": tags,
                "link_confidence": 1.0,
                "cv_domain_score": cv_domain_score(title, abstract),
                "strong_cv_domain_score": strong_cv_domain_score(title, abstract),
                "visual_evidence_score": visual_evidence_score(title, abstract),
            })
            existing_titles.add(title.lower())
    return papers


def add_known_recent_cv_extras(existing_titles: set[str]) -> list[dict]:
    known = [
        {
            "title": "Teacher-Guided Routing for Sparse Vision Mixture-of-Experts",
            "authors": "Kada et al.",
            "abstract": "A sparse vision Mixture-of-Experts framework that uses teacher-guided routing to stabilize expert assignment for computer vision models.",
            "venue": "CVPR",
            "year": 2026,
            "url": "https://openaccess.thecvf.com/content/CVPR2026/papers/Kada_Teacher-Guided_Routing_for_Sparse_Vision_Mixture-of-Experts_CVPR_2026_paper.pdf",
            "source": "manual CV web seed",
        },
        {
            "title": "FLoMo-Net: A Novel Task-Adaptive Mixture of Experts Routing Framework with Flow-Matching Optimization",
            "authors": "Ahmed et al.",
            "abstract": "A task-adaptive Mixture of Experts routing framework for vision tasks, using flow-matching optimization to guide expert selection.",
            "venue": "WACV",
            "year": 2026,
            "url": "https://openaccess.thecvf.com/content/WACV2026/papers/Ahmed_FLoMo-Net_A_Novel_Task-Adaptive_Mixture_of_Experts_Routing_Framework_with_WACV_2026_paper.pdf",
            "source": "manual CV web seed",
        },
        {
            "title": "Routers in Vision Mixture of Experts: An Empirical Study",
            "authors": "Riquelme et al.",
            "abstract": "An empirical study of router designs in vision Mixture-of-Experts models, comparing sparse and soft routing choices under computer vision workloads.",
            "venue": "arXiv cs.CV",
            "year": 2024,
            "url": "https://arxiv.org/abs/2401.15969",
            "source": "manual CV web seed",
        },
        {
            "title": "Scaling Vision with Sparse Mixture of Experts",
            "authors": "Riquelme et al.",
            "abstract": "Introduces V-MoE, a sparse Mixture-of-Experts variant of Vision Transformer that routes image patches to experts for scalable computer vision.",
            "venue": "NeurIPS",
            "year": 2021,
            "url": "https://arxiv.org/abs/2106.05974",
            "source": "manual CV web seed",
        },
    ]
    papers = []
    for idx, item in enumerate(known):
        if item["title"].lower() in existing_titles:
            continue
        tier, tags = classify_relevance(item["title"], item["abstract"])
        item.update({
            "id": f"known-{idx}",
            "tier": tier or "strict_moe",
            "tags": tags or ["manual-moe"],
            "link_confidence": 1.0,
            "cv_domain_score": cv_domain_score(item["title"], item["abstract"]),
            "strong_cv_domain_score": strong_cv_domain_score(item["title"], item["abstract"]),
            "visual_evidence_score": visual_evidence_score(item["title"], item["abstract"]),
        })
        papers.append(item)
        existing_titles.add(item["title"].lower())
    return papers


def summarize(papers: list[dict]) -> dict:
    by_year = Counter(str(p["year"] or "Unknown") for p in papers)
    by_venue = Counter(p["venue"] for p in papers)
    by_tier = Counter(p["tier"] for p in papers)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total": len(papers),
        "by_year": dict(sorted(by_year.items(), key=lambda kv: kv[0], reverse=True)),
        "by_venue": dict(by_venue.most_common()),
        "by_tier": dict(by_tier),
        "sources": [
            {
                "name": "choucisan/CVpaper",
                "url": "https://github.com/choucisan/CVpaper",
                "coverage": "CVPR 2013-2025, ICCV 2013-2025, ECCV 2018-2024",
            },
            {
                "name": "CVPR2026 hongsong miner",
                "url": "https://hongsong-wang.github.io/CVPR2026/",
                "coverage": "Local mined CVPR 2026 titles, abstracts, and links",
            },
            {
                "name": "arXiv cs.CV API",
                "url": "https://export.arxiv.org/api/query",
                "coverage": "CV-only keyword expansion",
            },
            {
                "name": "OpenAlex",
                "url": "https://openalex.org/",
                "coverage": "Conservative CV-filtered strict MoE keyword expansion",
            },
        ],
    }


def main() -> None:
    if not MAIN_CSV.exists():
        raise SystemExit(f"Missing CVpaper CSV: {MAIN_CSV}")

    link_records = load_link_records()
    papers = build_from_cvpaper(link_records)
    existing_titles = {p["title"].lower() for p in papers}

    papers.extend(build_from_cvpr2026_jsonl(existing_titles))
    papers.extend(fetch_arxiv_extras(existing_titles))
    papers.extend(fetch_openalex_extras(existing_titles))
    papers.extend(add_known_recent_cv_extras(existing_titles))

    papers.sort(key=lambda p: (p["year"] or 0, p["tier"] == "strict_moe", p["title"].lower()), reverse=True)
    summary = summarize(papers)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"summary": summary, "papers": papers}, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(papers)} papers to {OUT_JSON}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
