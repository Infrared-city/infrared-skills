# AGENTS.md

This repo holds runnable Python recipes and an agent skill (`use-infrared`) for the [Infrared SDK](https://pypi.org/project/infrared-sdk/).

## Audience

Two distinct audiences:

- **Skill consumers** — AI coding agents (Claude Code, Cursor, Codex, Copilot, Windsurf) helping end-users call the Infrared SDK in their own projects. They install the skill via the marketplace; they read `plugins/infrared/skills/use-infrared/SKILL.md` and load references on demand.
- **Repo contributors** — humans (or agents) editing this repo. Read this file.

## Project layout

```
.
├── README.md                                     human-facing landing
├── AGENTS.md                                     this file (contributor rules)
├── CLAUDE.md                            → AGENTS.md (symlink)
├── .claude-plugin/marketplace.json               Claude Code marketplace entry
├── plugins/infrared/                             the plugin
│   ├── .claude-plugin/plugin.json
│   └── skills/use-infrared/
│       ├── SKILL.md                              router
│       └── references/                           progressive disclosure
│           ├── 00-install-and-auth.md
│           ├── 01-quickstart.md
│           ├── 02-geometry-and-time.md
│           ├── analyses/                         per-analysis payload + result shape
│           ├── workflows/                        area API, async, result files
│           ├── interpretation/                   how to read the numbers
│           └── pitfalls/
├── examples/                                     runnable Python recipes (clone-and-run)
├── .cursor/rules/infrared.mdc        → ../../AGENTS.md (symlink)
├── .github/copilot-instructions.md   → ../AGENTS.md (symlink)
└── scripts/                                      install + sync helpers
```

## How to add a new example

- One file per recipe in `examples/`, prefixed `NN-name.py`.
- Must run end-to-end against the public PyPI `infrared-sdk` package (no internal forks).
- Header docstring: title, what it shows, expected runtime.
- Reads `INFRARED_API_KEY` from env, never hardcoded.
- Pure-Python deps; `pip install -r examples/requirements.txt` should be enough.

## How to add or edit a skill reference file

- Each reference under `plugins/infrared/skills/use-infrared/references/` is self-contained — an agent reading it should not need to fetch anything else.
- Include a working payload example and the response shape.
- Cite analysis name + SDK request class once at the top.
- Keep individual files under ~300 lines. Split by topic, not size.

## How to add or edit `SKILL.md`

- Keep `SKILL.md` itself under ~250 lines — it's the router.
- The frontmatter `description:` is what auto-activates the skill in Claude Code; list trigger keywords (analysis names, SDK function names, `infrared.city`, `infrared-sdk`, common user phrasings).
- Body = decision tree pointing at `references/...md` files.

## Code style

- Python 3.11+, ruff-formatted, type-hinted.
- All examples use the public SDK only — no internal Infrared modules.
- No internal URLs (no `api-test.infrared.city`, no `staging.*`, no Lambda function names, no DynamoDB table names).
- No hardcoded credentials, ever.

## Sync from the SDK repo

The private `infrared-api-sdk` repo runs a CI job that opens PRs against this repo (one-way). Do not edit `examples/` files that originate from the sync — edit them upstream and let the sync regenerate.

Files declared as sync targets are listed in `docs/sync-design.md`.

## What NOT to do

- Don't copy from `infrared-api-sdk/skills/infrared-sdk-contributors/` or `async-jobs.md` — those are internal.
- Don't reference internal Infrared infra, account IDs, or staging endpoints.
- Don't ship API keys in `.env.example` files — show the variable name only, never a value.
- Don't add a Co-Authored-By trailer on commits.
