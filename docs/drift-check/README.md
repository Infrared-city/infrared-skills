# Drift-check artifacts

Concrete inputs to the LLM-based drift-check flow that keeps `infrared-skills` in sync with `infrared-api-sdk`. These files are versioned **here** (alongside the content they reason about) and copied into the Windmill flow.

## What's in this folder

| File | Purpose |
|---|---|
| `schema.json` | JSON Schema for the LLM's response. Used in the API's structured-output mode (Anthropic tool-use input_schema, OpenAI `response_format: json_schema`). |
| `system-prompt.md` | The system prompt sent on every drift-check call. Tells the model what counts as drift, how to dedup against existing issues/PRs, and what actions to emit. |
| `flatten.py` | Flatten a repo into a single Markdown blob with path-encoded headings. Used to render both `infrared-api-sdk` and `infrared-skills` as one prompt section each. |
| `state-fetch.sh` | Fetch existing open drift-check issues + PRs from the skills repo as JSON. Output is appended to the user prompt so the model can dedup. |

## How they fit together (planned Windmill flow)

```
Trigger (cron or webhook on infrared-api-sdk PR-merged)
   │
   ▼
[1] flatten.py  infrared-api-sdk  →  sdk_blob.md
[2] flatten.py  infrared-skills   →  skills_blob.md
[3] state-fetch.sh                →  state.json
[4] build prompt:
        system  = system-prompt.md
        user    = sdk_blob + diff + skills_blob + state.json
        schema  = schema.json
[5] call LLM (Claude 4.7 1M ctx via Anthropic Foundry — primary)
[6] try parse + JSON-schema validate
        ├── ok  →  step 8
        └── fail → call cheap model (Haiku 4.5 / GPT-5-mini) to repair, validate again
[7] dispatch actions:
        new_issue   → gh issue create  --label drift-check,<severity>
        update_issue→ gh issue comment
        new_pr      → checkout branch, apply edits, gh pr create
        update_pr   → gh pr comment
        no_action   → log only
[8] write run record back to Windmill state (last commit checked, dispatch summary)
```

## Wire-up location (later, in the team Windmill repo)

```
ir-team-windmill/f/external_projects/infrared_skills_drift_check/
├── flatten.py             ← copied / symlinked from here
├── system-prompt.md       ← copied / symlinked from here
├── schema.json            ← copied / symlinked from here
├── state-fetch.sh         ← copied / symlinked from here
├── check_drift.py         ← built next: orchestrates steps [1]–[8]
└── flow.yaml              ← Windmill cron + webhook trigger config
```

Versioning the prompt + schema in this repo means a PR that changes the skills layout can update the drift-check inputs in the same commit.

## Cost estimate

| Item | Per run |
|---|---|
| Input tokens (full skills repo + SDK source + diff) | ~150–200K |
| Output tokens (JSON action list, typical) | ~1–4K |
| Anthropic Foundry pricing (Claude 4.7 1M ctx, indicative) | ~$0.50–1.00 |
| Fallback validator call (only on parse failure) | ~$0.01–0.05 |
| Weekly cron (52/yr) + per-PR (~5/wk × 52) = ~325 runs/yr | ~$160–325/yr |

Negligible compared to the cost of the agent making wrong claims to users.

## Status

Scaffolding only — no flow has been deployed yet. Next step: build `check_drift.py` (the orchestrator) and `flow.yaml` (the trigger config) in the team Windmill repo.
