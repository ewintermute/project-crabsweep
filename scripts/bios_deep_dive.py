#!/usr/bin/env python3
"""
bios_deep_dive.py — Run a deep BIOS analysis on a high-scoring post.

Usage:
    python3 scripts/bios_deep_dive.py <post_id>
    python3 scripts/bios_deep_dive.py --list-candidates   # show posts with crab_score >= threshold

The script prepends Neophyte Labs' constraints to the BIOS query so that
the analysis stays grounded in what we can actually do.
"""

import json
import os
import sys
import urllib.request
import time
from pathlib import Path

BASE_DIR    = Path(__file__).parent.parent
SCORED_FILE = BASE_DIR / "data" / "scored_posts.json"
CAPS_FILE   = BASE_DIR / "lab_capabilities.md"

BIOS_KEY    = os.environ.get("BIOS_API_KEY", "bio_sk_ItUmxSllzyHo0vnzltY4ZaqlbVDDuCAIndWqoRdgkvZG51QU")
BIOS_BASE   = "https://api.ai.bio.xyz"
CANDIDATE_THRESHOLD = 6.5


def load_db():
    if not SCORED_FILE.exists():
        return {"posts": []}
    return json.loads(SCORED_FILE.read_text())


def save_db(db):
    SCORED_FILE.write_text(json.dumps(db, indent=2))


def bios_request(method, path, payload=None):
    url = f"{BIOS_BASE}{path}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {BIOS_KEY}",
            "Content-Type": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def build_bios_query(post, lab_caps):
    """
    Prepend lab constraints to the BIOS query so the analysis respects
    what Neophyte Labs can actually do.
    """
    return f"""## Context: Neophyte Labs Experimental Constraints

Before analysing this hypothesis, note the following hard constraints on what we can test in-house:

{lab_caps}

Any suggested experiments MUST be compatible with these constraints. Flag clearly if the core hypothesis cannot be tested within them, and propose the closest feasible proxy experiment.

---

## Hypothesis to Analyse

**Title:** {post['title']}

{post.get('body_excerpt', '')}

---

## Analysis Request

1. Summarise the core scientific claim and what would constitute a test of it.
2. Review the existing literature — what is already known, and what is the evidence gap?
3. Propose a Minimum Viable Experiment (MVE) that Neophyte Labs could execute within our constraints ($50K, 2 months, 2 researchers, BSL-1, equipment list above).
4. Identify the single biggest experimental risk or confound.
5. Rate overall experimental priority for our lab (High / Medium / Low) with one-sentence justification.
"""


def list_candidates():
    db = load_db()
    candidates = [
        p for p in db["posts"]
        if p.get("crab_score", 0) >= CANDIDATE_THRESHOLD and not p.get("bios_analysis")
    ]
    candidates.sort(key=lambda x: x.get("crab_score", 0), reverse=True)
    if not candidates:
        print(f"No candidates with crab_score ≥ {CANDIDATE_THRESHOLD} awaiting BIOS analysis.")
        return
    print(f"\n{'Score':<7} {'Post ID':<38} Title")
    print("-" * 90)
    for p in candidates:
        print(f"{p['crab_score']:<7.1f} {p['post_id']:<38} {p['title'][:50]}")


def deep_dive(post_id):
    db = load_db()
    post = next((p for p in db["posts"] if p["post_id"] == post_id), None)
    if not post:
        print(f"[bios] Post {post_id} not found in scored_posts.json", file=sys.stderr)
        sys.exit(1)

    if post.get("bios_analysis"):
        print(f"[bios] Post {post_id} already has a BIOS analysis. Re-running anyway.")

    lab_caps = CAPS_FILE.read_text()
    query = build_bios_query(post, lab_caps)

    print(f"[bios] Starting deep research for: {post['title'][:70]}…")
    print(f"[bios] CrabScore: {post.get('crab_score', '?')}")

    # Start async deep research
    resp = bios_request("POST", "/deep-research/start", {
        "query": query,
        "mode": "semi-autonomous",
    })
    conv_id = resp.get("conversationId") or resp.get("id")
    if not conv_id:
        print(f"[bios] Failed to start research: {resp}", file=sys.stderr)
        sys.exit(1)

    print(f"[bios] Research started (conversationId: {conv_id}). Polling…")

    # Poll until done (max 5 min)
    for attempt in range(30):
        time.sleep(10)
        result = bios_request("GET", f"/deep-research/{conv_id}")
        status = result.get("status", "")
        msgs = result.get("messages", [])
        print(f"  [{attempt+1}] status={status}, messages={len(msgs)}")
        if status in ("completed", "done", "finished") or (msgs and status not in ("running", "in_progress", "pending")):
            break
    else:
        print("[bios] Timed out waiting for research to complete.", file=sys.stderr)

    # Extract final answer from messages
    final_text = ""
    for msg in reversed(result.get("messages", [])):
        role = msg.get("role", "")
        if role in ("assistant", "agent", "system"):
            final_text = msg.get("content", "")
            break

    # Store in db
    post["bios_analysis"] = {
        "conversation_id": conv_id,
        "query":           query[:500] + "…",
        "result":          final_text,
        "analysed_at":     __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    save_db(db)
    print(f"\n[bios] Analysis complete. Saved to scored_posts.json.")
    print(f"\n{'='*70}\n{final_text[:2000]}\n{'='*70}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "--list-candidates":
        list_candidates()
    else:
        deep_dive(sys.argv[1])
