# AGENTS.md

Repo: agent skills + Python recipes for the [Infrared SDK](https://github.com/Infrared-city/infrared-api-sdk).

## For agents working with the Infrared SDK in any project

Read [`plugins/infrared/skills/use-infrared/SKILL.md`](plugins/infrared/skills/use-infrared/SKILL.md). It has:
- Quick start (paste-ready Python)
- Invariants (auth, coords, imports, enums)
- Decision tree for picking an analysis
- Pointers to per-analysis interpretation references

That file is the canonical SDK-usage guide. Codex CLI / Copilot / Windsurf agents reading this AGENTS.md should also pull SKILL.md content into context.

## For contributors editing this repo

- One file per recipe in `examples/`, prefixed `NN-name.py`. Reads `INFRARED_API_KEY` from env, never hardcoded.
- Each reference under `plugins/infrared/skills/use-infrared/references/` is self-contained — keep them short.
- `SKILL.md` is the router; keep it under ~80 lines.
- Python 3.11+, ruff format, type hints. Public SDK only — no internal Infrared modules. No internal URLs (no `api-test.*`, no Lambda function names, etc).
- No API keys in any file, ever.

## Do not port from

- `infrared-api-sdk/skills/infrared-sdk-contributors/` — internal.
- `infrared-api-sdk/skills/async-jobs.md` — internal infrastructure.
