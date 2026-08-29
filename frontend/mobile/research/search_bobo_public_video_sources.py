#!/usr/bin/env python3
"""Search public video platforms for Bobo Principal research and persist raw results."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append("/opt/.manus/.sandbox-runtime")
from data_api import ApiClient  # type: ignore

OUTPUT_DIR = Path(__file__).resolve().parent / "public-video-results"
QUERIES = ["波波校长 榜样教育", "21天智慧父母成长营"]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = ApiClient()
    summary: list[dict[str, object]] = []

    for index, query in enumerate(QUERIES, start=1):
        youtube = client.call_api(
            "Youtube/search",
            query={"q": query, "hl": "zh-CN", "gl": "CN"},
        )
        youtube_path = OUTPUT_DIR / f"youtube-{index}.json"
        youtube_path.write_text(json.dumps(youtube, ensure_ascii=False, indent=2), encoding="utf-8")

        tiktok = client.call_api(
            "Tiktok/search_tiktok_video_general",
            query={"keyword": query},
        )
        tiktok_path = OUTPUT_DIR / f"tiktok-{index}.json"
        tiktok_path.write_text(json.dumps(tiktok, ensure_ascii=False, indent=2), encoding="utf-8")

        summary.append(
            {
                "query": query,
                "youtube_result_count": len(youtube.get("contents", [])) if isinstance(youtube, dict) else 0,
                "tiktok_result_count": len(tiktok.get("data", [])) if isinstance(tiktok, dict) else 0,
                "youtube_file": str(youtube_path),
                "tiktok_file": str(tiktok_path),
            }
        )

    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary_path)


if __name__ == "__main__":
    main()
