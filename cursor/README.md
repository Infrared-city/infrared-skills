# Cursor rule for the Infrared SDK

Drop the single file `infrared.mdc` in this folder into your project's `.cursor/rules/` directory and Cursor will load it whenever you mention Infrared.

## Install

### Option A — copy the file

```bash
mkdir -p .cursor/rules
curl -fsSL https://raw.githubusercontent.com/Infrared-city/infrared-skills/main/cursor/infrared.mdc \
  -o .cursor/rules/infrared.mdc
```

### Option B — clone the whole repo and symlink

```bash
git clone git@github.com:Infrared-city/infrared-skills.git
mkdir -p .cursor/rules
ln -s "$(pwd)/infrared-skills/cursor/infrared.mdc" .cursor/rules/infrared.mdc
```

Symlinking lets you `git pull` to get rule updates automatically.

## What it does

`infrared.mdc` is an **Agent-Requested** rule (frontmatter `description:` only, `alwaysApply: false`). Cursor loads it on demand when its description matches what you're asking — e.g. "run a wind sim with Infrared", "interpret UTCI results", "what's the PWC Lawson scale" — without burning context on every other turn.

It contains:
- Invariants (auth header, lon/lat order, kebab-case enums)
- Quick-start payload
- Result interpretation cheat-sheet for all 8 analyses
- Common pitfalls

For richer progressive-disclosure docs, use Claude Code (`/plugin install infrared@infrared-skills`) — that loads the same content as 20+ on-demand reference files via the `use-infrared` skill.

## Updating

When the rule is updated upstream, just re-run the `curl` (Option A) or `git pull` in the cloned repo (Option B).
