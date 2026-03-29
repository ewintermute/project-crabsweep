#!/usr/bin/env python3
"""
fetch_posts.py — Pull new posts from Beach.Science and write to data/pending_posts.json.
Does NOT score. Scoring is done by the agent in the cron turn.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BEACH_API  = "https://beach.science/api/v1"
BEACH_KEY  = os.environ.get("BEACH_SCIENCE_API_KEY", "beach_zzdMT390xQ6soMtpRz1TU2pi6uQAZQ2Z")
FETCH_LIMIT = 40
SORTS = ["latest", "breakthrough"]

BASE_DIR     = Path(__file__).parent.parent
SCORED_FILE  = BASE_DIR / "data" / "scored_posts.json"
PENDING_FILE = BASE_DIR / "data" / "pending_posts.json"


def beach_get(path, params=None):
    url = f"{BEACH_API}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {BEACH_KEY}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def load_existing_ids():
    if SCORED_FILE.exists():
        db = json.loads(SCORED_FILE.read_text())
        return {p["post_id"] for p in db.get("posts", [])}
    return set()


def run():
    existing_ids = load_existing_ids()
    seen = set(existing_ids)
    new_posts = []

    for sort in SORTS:
        try:
            result = beach_get("/posts", {"limit": FETCH_LIMIT, "sort": sort, "type": "hypothesis"})
            posts = result if isinstance(result, list) else result.get("posts", result.get("items", []))
            print(f"[fetch] [{sort}] got {len(posts)} posts", file=sys.stderr)
            for p in posts:
                pid = str(p.get("id") or p.get("post_id", ""))
                if pid and pid not in seen:
                    seen.add(pid)
                    author = p.get("author", {})
                    new_posts.append({
                        "post_id":      pid,
                        "title":        p.get("title", ""),
                        "body":         p.get("body", ""),
                        "author":       author.get("handle", "") if isinstance(author, dict) else str(author),
                        "post_url":     f"https://beach.science/post/{pid}",
                        "created_at":   p.get("created_at", ""),
                        "likes":        p.get("like_count", p.get("likes", 0)),
                        "comments":     p.get("comment_count", p.get("comments", 0)),
                    })
        except Exception as e:
            print(f"[fetch] [{sort}] error: {e}", file=sys.stderr)

    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(json.dumps({"posts": new_posts, "fetched_at": datetime.now(timezone.utc).isoformat()}, indent=2))
    print(f"[fetch] {len(new_posts)} new posts written to pending_posts.json")
    return len(new_posts)


if __name__ == "__main__":
    n = run()
    sys.exit(0 if n >= 0 else 1)
