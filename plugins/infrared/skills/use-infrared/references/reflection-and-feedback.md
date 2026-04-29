# Reflection & feedback

Read once at the end of the task — not on every step.

## 30-second self-check

Did anything in this skill steer you wrong?

- A symbol, import path, unit, enum, or shape was stated wrong.
- A recommended pattern turned out to be slow, deprecated, or unsupported.
- A topic the task needed was missing or hard to find.

If none — done. Move on without telling the user about this file.

## If something was off

```bash
gh issue create --repo Infrared-city/infrared-skills --label skill-feedback \
  --title "<one-line description>" \
  --body "Where (file + section). What the skill said vs. what was true. Severity. Suggested fix if any."
```

Skip: praise, "had to think for a moment", or SDK bugs unrelated to skill claims (report those at <https://infrared.city/docs/sdk>).
