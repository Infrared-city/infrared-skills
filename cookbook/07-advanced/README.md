# 07 — Advanced: lower-level primitives

Six worked examples of the SDK's lower-level primitives, for users who want full control over the pipeline:

1. Single-tile manual submit / poll / download
2. Area composable primitives (submit / poll / merge separately)
3. Full manual tile-by-tile pipeline
4. BYO (bring-your-own) weather data for thermal analyses
5. Persist and resume schedules across sessions
6. Webhook-driven area workflow

Use these only when `run_area_and_wait` doesn't fit your needs — the high-level API handles 95% of cases.

**Run:** `python advanced_usage.py`
**Deps:** `infrared-sdk numpy python-dotenv`
