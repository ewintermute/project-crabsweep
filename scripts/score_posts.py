#!/usr/bin/env python3
"""
score_posts.py — Read pending_posts.json, score each post, append to scored_posts.json.

This script is intended to be called BY the agent (not standalone), because the agent
IS the LLM. The agent reads this script's prompt template, scores each post itself,
and calls this script with the results as JSON on stdin.

Usage (agent calls this):
    echo '<json>' | python3 scripts/score_posts.py --commit

Or in dry-run mode (just print prompt for agent):
    python3 scripts/score_posts.py --prompt
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR     = Path(__file__).parent.parent
SCORED_FILE  = BASE_DIR / "data" / "scored_posts.json"
PENDING_FILE = BASE_DIR / "data" / "pending_posts.json"
CAPS_FILE    = BASE_DIR / "lab_capabilities.md"

SCORE_SCHEMA = """{
  "post_id": "<same as input>",
  "feasibility": <0-10>,
  "relevance": <0-10>,
  "novelty": <0-10>,
  "mve_ability": <0-10>,
  "crab_score": <weighted: feasibility*0.35 + relevance*0.25 + novelty*0.2 + mve_ability*0.2>,
  "rationale": "<2-3 sentences: why this scored the way it did, referencing specific lab constraints>",
  "suggested_mve": "<one sentence: the simplest experiment to test the core claim within our constraints>"
}"""


def build_prompt(posts, lab_caps):
    post_block = "\n\n".join(
        f"POST {i+1} (id: {p['post_id']})\nTitle: {p['title']}\nBody: {p['body'][:1500]}"
        for i, p in enumerate(posts)
    )
    return f"""You are a research strategist at Neophyte Labs. Score each Beach.Science hypothesis post against our lab's capabilities and constraints.

## Lab Capabilities & Constraints

{lab_caps}

## Scoring Dimensions (each 0–10)

- **feasibility**: Can this be done within BSL-1, $50K budget, 2 months, 2 researchers, with our equipment list?
- **relevance**: Does the topic match our wet-lab skills (microbiology, molecular biology, basic cell culture)?
- **novelty**: Is this an interesting, underexplored angle worth pursuing?
- **mve_ability**: Can we design a tight Minimum Viable Experiment to test the core claim? Lower if it requires specialized equipment, clinical access, or advanced computation we don't have.

**crab_score** = feasibility×0.35 + relevance×0.25 + novelty×0.2 + mve_ability×0.2

Be strict about feasibility — penalize heavily for anything requiring flow cytometry, confocal microscopy, clinical samples, HPC, or BSL-2+ organisms. Reward hypotheses that can be tested with plates, PCR, qPCR, basic spectrophotometry, or simple microbiology.

## Posts to Score

{post_block}

## Output

Return a JSON array — one object per post, in the same order, using this schema for each:
{SCORE_SCHEMA}

Return ONLY the JSON array. No prose, no markdown fences.
"""


def load_pending():
    if not PENDING_FILE.exists():
        return []
    return json.loads(PENDING_FILE.read_text()).get("posts", [])


def load_scored():
    if SCORED_FILE.exists():
        return json.loads(SCORED_FILE.read_text())
    return {"posts": [], "last_run": None, "total": 0}


def commit(scored_results):
    """Merge scored results into scored_posts.json."""
    db = load_scored()
    existing_ids = {p["post_id"] for p in db["posts"]}
    pending = load_pending()
    pending_map = {p["post_id"]: p for p in pending}

    added = 0
    for result in scored_results:
        pid = result.get("post_id")
        if not pid or pid in existing_ids:
            continue
        base = pending_map.get(pid, {})
        record = {
            "post_id":      pid,
            "title":        base.get("title", ""),
            "body_excerpt": base.get("body", "")[:400],
            "author":       base.get("author", ""),
            "post_url":     base.get("post_url", f"https://beach.science/post/{pid}"),
            "created_at":   base.get("created_at", ""),
            "likes":        base.get("likes", 0),
            "comments":     base.get("comments", 0),
            "scored_at":    datetime.now(timezone.utc).isoformat(),
            "feasibility":  result.get("feasibility", 0),
            "relevance":    result.get("relevance", 0),
            "novelty":      result.get("novelty", 0),
            "mve_ability":  result.get("mve_ability", 0),
            "crab_score":   result.get("crab_score", 0),
            "rationale":    result.get("rationale", ""),
            "suggested_mve": result.get("suggested_mve", ""),
            "bios_analysis": None,  # populated by bios_deep_dive.py
        }
        db["posts"].append(record)
        existing_ids.add(pid)
        added += 1

    db["posts"].sort(key=lambda x: x.get("crab_score", 0), reverse=True)
    db["last_run"] = datetime.now(timezone.utc).isoformat()
    db["total"] = len(db["posts"])
    SCORED_FILE.write_text(json.dumps(db, indent=2))

    # Mirror to docs/data/ for GitHub Pages
    docs_data = BASE_DIR / "docs" / "data" / "scored_posts.json"
    docs_data.parent.mkdir(parents=True, exist_ok=True)
    docs_data.write_text(json.dumps(db, indent=2))

    # Clear pending
    PENDING_FILE.write_text(json.dumps({"posts": [], "fetched_at": None}, indent=2))
    print(f"[score] committed {added} new scored posts ({db['total']} total)")
    return added


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--prompt"

    if mode == "--prompt":
        posts = load_pending()
        if not posts:
            print("[score] No pending posts.")
            sys.exit(0)
        lab_caps = CAPS_FILE.read_text()
        print(build_prompt(posts, lab_caps))

    elif mode == "--commit":
        # Read JSON scores from stdin
        raw = sys.stdin.read().strip()
        try:
            scored = json.loads(raw)
            if not isinstance(scored, list):
                scored = [scored]
            n = commit(scored)
            sys.exit(0 if n >= 0 else 1)
        except json.JSONDecodeError as e:
            print(f"[score] JSON parse error: {e}", file=sys.stderr)
            print(f"Input was: {raw[:200]}", file=sys.stderr)
            sys.exit(1)

    elif mode == "--pending-count":
        posts = load_pending()
        print(len(posts))
