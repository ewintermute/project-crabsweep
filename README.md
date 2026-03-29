# Project Crabsweep 🦀

**Purpose:** Periodically scan Beach.Science posts, evaluate each against Neophyte Labs' capabilities and constraints, score them for experimental feasibility, and surface the best opportunities in a web dashboard.

---

## How It Works

1. **Fetch** — Pull recent posts from the Beach.Science API (`/api/v1/posts`)
2. **Score** — Evaluate each post against `lab_capabilities.md` using an LLM scoring pass
3. **Store** — Append results to `data/scored_posts.json`
4. **Serve** — Static HTML dashboard reads `data/scored_posts.json` and renders a ranked table

## Scoring Criteria

Each post is scored 0–10 on:

- **Feasibility** — Can it be done within BSL-1, 2 months, $50K, 2 researchers?
- **Relevance** — Does it match our equipment and skill set?
- **Novelty** — Is it an interesting, underexplored angle?
- **MVE-ability** — Can we design a Minimum Viable Experiment to test it?

A composite **CrabScore** (weighted average) ranks posts.

## Files

```
project-crabsweep/
├── README.md
├── lab_capabilities.md         ← copy of Neophyte Labs constraints (reference)
├── scripts/
│   └── sweep.py                ← main sweep script (fetch + score + save)
├── data/
│   └── scored_posts.json       ← scored post records (appended on each run)
└── dashboard/
    └── index.html              ← static web dashboard
```

## Running Manually

```bash
cd "/home/node/workspace/2026-03-29 project-crabsweep"
python3 scripts/sweep.py
```

## Cron

A cron job runs `sweep.py` on a schedule (set up via OpenClaw cron).
Results are immediately reflected in the dashboard.

## Dashboard

Open `dashboard/index.html` in a browser, or serve it:
```bash
cd dashboard && python3 -m http.server 8080
```
