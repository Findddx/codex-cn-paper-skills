#!/usr/bin/env python3
"""Helpers for CNKI search manifests and download file matching.

This script intentionally avoids browser automation. Codex should use the
visible browser plus Chrome DevTools MCP for CNKI operations, then use this
helper only for local manifests and downloaded files.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any


PUNCT_RE = re.compile(r"[\s\u3000《》〈〉“”\"'‘’·,，.。:：;；!?！？()\[\]【】{}<>《》—\-_/\\|]+")
BAD_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def normalize_title(value: str) -> str:
    return PUNCT_RE.sub("", (value or "").strip()).lower()


def safe_filename(value: str, limit: int = 140) -> str:
    value = BAD_FILENAME_RE.sub("_", value or "")
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        value = "untitled"
    return value[:limit].rstrip(" .")


def parse_number(value: Any) -> int:
    text = str(value or "").replace(",", "")
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else 0


def extract_records(data: Any, inherited: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    inherited = inherited or {}
    if isinstance(data, list):
        rows: list[dict[str, Any]] = []
        for item in data:
            rows.extend(extract_records(item, inherited))
        return rows

    if not isinstance(data, dict):
        return []

    context = dict(inherited)
    for key in ("query", "total", "page"):
        if key in data and key not in context:
            context[key] = data[key]

    if data.get("title"):
        record = dict(context)
        record.update(data)
        return [record]

    rows: list[dict[str, Any]] = []
    for value in data.values():
        if isinstance(value, (dict, list)):
            rows.extend(extract_records(value, context))
    return rows


def load_json_or_csv(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]

    data = json.loads(path.read_text(encoding="utf-8"))
    rows = extract_records(data)
    if rows:
        return rows
    raise ValueError(f"Unsupported manifest structure: {path}")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def score_item(item: dict[str, Any], keywords: list[str]) -> float:
    title = str(item.get("title") or "")
    source = str(item.get("source") or item.get("journal") or "")
    authors = str(item.get("authors") or "")
    haystack = f"{title} {source} {authors}"
    norm_haystack = normalize_title(haystack)
    score = 0.0

    for kw in keywords:
        norm_kw = normalize_title(kw)
        if not norm_kw:
            continue
        if norm_kw in normalize_title(title):
            score += 20
        elif norm_kw in norm_haystack:
            score += 8

    citations = parse_number(item.get("citations") or item.get("quote"))
    downloads = parse_number(item.get("downloads") or item.get("download"))
    score += min(12.0, math.log1p(citations) * 3)
    score += min(8.0, math.log1p(downloads) * 1.2)

    if re.search(r"CSSCI|核心|北大|C刊|学报", source, re.I):
        score += 5
    if re.search(r"硕士|博士|学位", source):
        score += 2
    return round(score, 3)


def select_candidates(args: argparse.Namespace) -> None:
    keywords = [x.strip() for part in args.keywords for x in re.split(r"[,，;；\s]+", part) if x.strip()]
    collected: list[dict[str, Any]] = []
    for source_path in args.results:
        for item in load_json_or_csv(Path(source_path)):
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            normalized = normalize_title(title)
            record = dict(item)
            record["normalized_title"] = normalized
            record["score"] = max(float(record.get("score") or 0), score_item(record, keywords))
            collected.append(record)

    best_by_title: dict[str, dict[str, Any]] = {}
    for item in collected:
        key = item["normalized_title"]
        current = best_by_title.get(key)
        if current is None or float(item.get("score") or 0) > float(current.get("score") or 0):
            best_by_title[key] = item

    queue = sorted(best_by_title.values(), key=lambda x: float(x.get("score") or 0), reverse=True)
    if args.limit:
        queue = queue[: args.limit]

    output_rows: list[dict[str, Any]] = []
    for index, item in enumerate(queue, 1):
        output_rows.append(
            {
                "id": f"cnki-{index:04d}",
                "title": item.get("title", ""),
                "authors": item.get("authors", ""),
                "source": item.get("source") or item.get("journal", ""),
                "date": item.get("date", ""),
                "href": item.get("href", ""),
                "query": item.get("query", ""),
                "score": item.get("score", 0),
                "status": "pending",
                "note": "",
            }
        )

    write_json(Path(args.out), output_rows)
    if args.csv_out:
        write_csv(Path(args.csv_out), output_rows)
    print(f"selected={len(output_rows)} out={args.out}")


def parse_since(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return parsed.timestamp()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for i in range(1, 1000):
        candidate = path.with_name(f"{stem}_{i:03d}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create unique path for {path}")


def candidate_files(download_dir: Path, since_ts: float | None) -> list[Path]:
    files: list[Path] = []
    for path in download_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() in {".crdownload", ".tmp", ".part"}:
            continue
        if path.suffix.lower() not in {".pdf", ".caj"}:
            continue
        if since_ts is not None and path.stat().st_mtime < since_ts:
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.stat().st_mtime)


def best_match(path: Path, queue: list[dict[str, Any]]) -> dict[str, Any] | None:
    file_key = normalize_title(path.stem)
    best: tuple[int, dict[str, Any]] | None = None
    for item in queue:
        title_key = normalize_title(str(item.get("title") or ""))
        if not title_key:
            continue
        score = 0
        if title_key == file_key:
            score = 1000
        elif title_key in file_key:
            score = 800 + len(title_key)
        elif file_key in title_key and len(file_key) >= 8:
            score = 500 + len(file_key)
        if score and (best is None or score > best[0]):
            best = (score, item)
    return best[1] if best else None


def move_downloads(args: argparse.Namespace) -> None:
    download_dir = Path(args.download_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    queue = load_json_or_csv(Path(args.queue).expanduser().resolve()) if args.queue else []
    since_ts = parse_since(args.since)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_started_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    items: list[dict[str, Any]] = []

    quarantine_dir: Path | None = None
    if args.quarantine_caj:
        quarantine_dir = Path(args.quarantine_caj).expanduser().resolve()
        quarantine_dir.mkdir(parents=True, exist_ok=True)

    for source in candidate_files(download_dir, since_ts):
        ext = source.suffix.lower()
        match = best_match(source, queue)
        title = str(match.get("title") or "") if match else ""
        authors = str(match.get("authors") or "") if match else ""
        href = str(match.get("href") or "") if match else ""

        if ext == ".caj" and args.pdf_only:
            status = "skipped_caj_only"
            output_file = ""
            if quarantine_dir:
                dest = unique_path(quarantine_dir / source.name)
                if not args.dry_run:
                    shutil.move(str(source), str(dest))
                output_file = str(dest)
                status = "quarantined_caj"
            items.append(
                {
                    "title": title,
                    "status": status,
                    "source_file": str(source),
                    "output_file": output_file,
                    "href": href,
                    "message": "CAJ found during PDF-only run",
                }
            )
            continue

        if ext == ".pdf":
            if match:
                base = safe_filename("_".join(x for x in [title, authors] if x))
            else:
                base = safe_filename(source.stem)
            dest = unique_path(output_dir / f"{base}{source.suffix.lower()}")
            if not args.dry_run:
                shutil.move(str(source), str(dest))
            items.append(
                {
                    "title": title or source.stem,
                    "status": "downloaded_pdf" if match else "unmatched_pdf",
                    "source_file": str(source),
                    "output_file": str(dest),
                    "href": href,
                    "message": "" if match else "No reliable queue title match",
                }
            )

    manifest = {
        "run_started_at": run_started_at,
        "download_dir": str(download_dir),
        "output_dir": str(output_dir),
        "pdf_only": bool(args.pdf_only),
        "dry_run": bool(args.dry_run),
        "items": items,
    }
    write_json(manifest_path, manifest)
    if args.csv_out:
        write_csv(Path(args.csv_out), items)
    print(f"processed={len(items)} manifest={manifest_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CNKI manifest and download helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    select = sub.add_parser("select-candidates", help="deduplicate and score CNKI search results")
    select.add_argument("--results", nargs="+", required=True, help="JSON/CSV search result files")
    select.add_argument("--keywords", nargs="*", default=[], help="keywords used for scoring")
    select.add_argument("--limit", type=int, default=0, help="maximum queue size")
    select.add_argument("--out", required=True, help="output queue JSON")
    select.add_argument("--csv-out", help="optional output queue CSV")
    select.set_defaults(func=select_candidates)

    move = sub.add_parser("move-downloads", help="move current-run PDF downloads into output dir")
    move.add_argument("--download-dir", required=True)
    move.add_argument("--output-dir", required=True)
    move.add_argument("--queue", help="queue JSON/CSV used to match titles")
    move.add_argument("--manifest", required=True)
    move.add_argument("--csv-out", help="optional CSV manifest")
    move.add_argument("--since", help="ISO datetime or epoch seconds; only process newer files")
    move.add_argument("--pdf-only", action="store_true", help="do not accept CAJ as success")
    move.add_argument("--quarantine-caj", help="optional directory to move current-run CAJ files")
    move.add_argument("--dry-run", action="store_true")
    move.set_defaults(func=move_downloads)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
