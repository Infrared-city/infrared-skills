# AGENTS.md

Repo: agent skill and cookbook for the [Infrared SDK](https://infrared.city/docs/sdk/) (Python `pip install infrared-sdk`, TypeScript `npm install @infrared-city/infrared-sdk-ts`).

## For agents working with the Infrared SDK in any project

Read [`plugins/infrared/skills/use-infrared/SKILL.md`](plugins/infrared/skills/use-infrared/SKILL.md). It has:
- A router: "What do you want to build?"
- Concepts: analyses, inputs, tiling, results, cost
- Python and TypeScript quick starts
- Links to the references and to the docs site

Codex CLI, Copilot, and Windsurf agents that read this file must also load SKILL.md.

## For contributors editing this repo

- Recipes live in `cookbook/notebooks/`, `cookbook/scripts/`, and `cookbook/apps/`. Read `INFRARED_API_KEY` from the environment. Never hardcode it.
- Each reference under `plugins/infrared/skills/use-infrared/references/` is self-contained and short.
- `SKILL.md` is the router. Keep it at 130 lines or fewer. Put depth in `references/`.
- Link to the docs site (<https://infrared.city/docs/sdk/>). Do not copy API detail into this repo.
- Every file is 400 lines or fewer. Split larger files.
- Run code for real before you commit. Call `preview_area` first, and read the cost.
- Write prose in ASD-STE100 Simplified Technical English. Python 3.11+, ruff format, type hints. Public SDK only.
- No internal URLs (no staging or test hosts, no Lambda names, no internal repo paths). No API keys, no customer names.
