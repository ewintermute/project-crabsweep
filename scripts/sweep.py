#!/usr/bin/env python3
"""
Crabsweep — fetch Beach.Science posts, score against Neophyte Labs capabilities,
save to data/scored_posts.json.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────

BEACH_API   = "https://beach.science/api/v1"
BEACH_KEY   = os.environ.get("BEACH_SCIENCE_API_KEY", "beach_zzdMT390xQ6soMtpRz1TU2pi6uQAZQ2Z")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")

BASE_DIR    = Path(__file__).parent.parent
DATA_FILE   = BASE_DIR / "data" / "scored_posts.json"
CAPS_FILE   = BASE_DIR / "lab_capabilities.md"

FETCH_LIMIT = 40   # posts to fetch per run
SORTS       = ["latest", "breakthrough"]  # fetch both feeds

# ── Scoring prompt ───────────────────────────────────────────────────────────

LAB_CAPS = CAPS_FILE.read_text()

SCORE_PROMPT = """You are a research strategist at Neophyte Labs. Given a Beach.Science post and the lab's capabilities, score the post on four dimensions (each 0-10) and give a brief rationale.

LAB CAPABILITIES:
{caps}

POST TITLE: {title}
POST BODY: {body}

Return ONLY valid JSON with this exact structure:
{{
  "feasibility": <0-10>,
  "relevance": <0-10>,
  "novelty": <0-10>,
  "mve_ability": <0-10>,
  "crab_score": <weighted average: feasibility*0.35 + relevance*0.25 + novelty*0.2 + mve_ability*0.2>,
  "rationale": "<2-3 sentence summary of why this scored the way it did>",
  "suggested_mve": "<one sentence: the simplest experiment to test the core claim>"
}}
"""

# ── Helpers ──────────────────────────────────────────────────────────────────

def beach_get(path, params=None):
    url = f"{BEACH_API}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {BEACH_KEY}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def llm_score(title, body):
    """Score a post via OpenRouter (claude-haiku for speed/cost)."""
    if not OPENROUTER_KEY:
        # Fallback: return neutral scores with a note
        return {
            "feasibility": 5, "relevance": 5, "novelty": 5, "mve_ability": 5,
            "crab_score": 5.0,
            "rationale": "No OPENROUTER_API_KEY set — scores are placeholder only.",
            "suggested_mve": "N/A"
        }

    prompt = SCORE_PROMPT.format(caps=LAB_CAPS, title=title, body=body[:3000])
    payload = json.dumps({
        "model": "anthropic/claude-haiku-4",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
        "temperature": 0.2,
    }).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    text = data["choices"][0]["message"]["content"].strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def load_existing():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"posts": [], "last_run": None}


def save(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2))


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    print(f"[crabsweep] Starting — {datetime.now(timezone.utc).isoformat()}")
    db = load_existing()
    existing_ids = {p["post_id"] for p in db["posts"]}

    new_posts = []
    for sort in SORTS:
        try:
            result = beach_get("/posts", {"limit": FETCH_LIMIT, "sort": sort, "type": "hypothesis"})
            posts = result if isinstance(result, list) else result.get("posts", result.get("items", []))
            print(f"  [{sort}] fetched {len(posts)} posts")
            for p in posts:
                pid = str(p.get("id") or p.get("post_id", ""))
                if pid and pid not in existing_ids:
                    new_posts.append(p)
                    existing_ids.add(pid)
        except Exception as e:
            print(f"  [{sort}] fetch error: {e}", file=sys.stderr)

    print(f"  {len(new_posts)} new posts to score")

    for p in new_posts:
        pid   = str(p.get("id") or p.get("post_id", ""))
        title = p.get("title", "")
        body  = p.get("body", "")
        author = p.get("author", {})
        author_handle = author.get("handle", "") if isinstance(author, dict) else str(author)

        print(f"  Scoring: [{pid}] {title[:60]}…")
        try:
            scores = llm_score(title, body)
        except Exception as e:
            print(f"    scoring error: {e}", file=sys.stderr)
            scores = {
                "feasibility": 0, "relevance": 0, "novelty": 0, "mve_ability": 0,
                "crab_score": 0, "rationale": f"Scoring error: {e}", "suggested_mve": ""
            }

        record = {
            "post_id":       pid,
            "title":         title,
            "body_excerpt":  body[:400],
            "author":        author_handle,
            "post_url":      f"https://beach.science/post/{pid}",
            "created_at":    p.get("created_at", ""),
            "likes":         p.get("like_count", p.get("likes", 0)),
            "comments":      p.get("comment_count", p.get("comments", 0)),
            "scored_at":     datetime.now(timezone.utc).isoformat(),
            **scores,
        }
        db["posts"].append(record)

    # Sort by crab_score descending
    db["posts"].sort(key=lambda x: x.get("crab_score", 0), reverse=True)
    db["last_run"] = datetime.now(timezone.utc).isoformat()
    db["total"] = len(db["posts"])

    save(db)
    print(f"[crabsweep] Done — {len(db['posts'])} total posts in DB, {len(new_posts)} new")


if __name__ == "__main__":
    run()
