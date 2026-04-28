# Infrared Skills

Agent skills and Python recipes for the [Infrared SDK](https://pypi.org/project/infrared-sdk/) — urban microclimate analysis (wind, solar, thermal comfort) for AI coding agents.

> **Status:** incubation (private). Will flip public when content is reviewed.

## Install the SDK

```bash
pip install infrared-sdk
export INFRARED_API_KEY=...   # get one at https://infrared.city
```

## Run an example

```bash
git clone git@github.com:Infrared-city/infrared-skills.git
cd infrared-skills
pip install -r examples/requirements.txt
python examples/01-quickstart-wind.py
```

## Install the agent skill

### Claude Code

```text
/plugin marketplace add Infrared-city/infrared-skills
/plugin install infrared@infrared-skills
```

After install, Claude Code will auto-activate the `use-infrared` skill whenever you mention Infrared, urban microclimate analysis, wind / solar / thermal comfort simulation, or the `infrared-sdk` package.

### Cursor

Drop a single rule file into your project — Cursor will activate it whenever you mention Infrared:

```bash
mkdir -p .cursor/rules
curl -fsSL https://raw.githubusercontent.com/Infrared-city/infrared-skills/main/cursor/infrared.mdc \
  -o .cursor/rules/infrared.mdc
```

See [`cursor/README.md`](./cursor/README.md) for details.

### Codex / Copilot / Windsurf

The `AGENTS.md` at the repo root is read by Codex CLI, Copilot, and Windsurf when you clone this repo into your workspace. A universal installer is planned (`curl https://infrared.city/skills.sh | bash`).

## What's in here

- **`plugins/infrared/skills/use-infrared/`** — the agent skill (Anthropic Agent Skills format). Self-contained references for every analysis (wind, PWC, solar radiation, daylight, sun hours, SVF, UTCI, TCS), the Area API, async jobs, result interpretation, and common pitfalls.
- **`examples/`** — runnable Python recipes you can clone and run.
- **`AGENTS.md`** — contributor rules for this repo.

## Docs

Full SDK reference: <https://infrared.city/docs/sdk> (publishing soon).

## License

Apache-2.0 — see [LICENSE](./LICENSE).
