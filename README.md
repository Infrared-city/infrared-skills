# Infrared Skills

Agent skills and Python recipes for the [Infrared SDK](https://pypi.org/project/infrared-sdk/) — urban microclimate analysis (wind, solar, thermal comfort).

> **Status:** incubation (private). Will flip public when content is reviewed.

## Install the SDK

```bash
pip install infrared-sdk
export INFRARED_API_KEY=...   # https://infrared.city
```

## Install the agent skill

### Claude Code

```text
/plugin marketplace add Infrared-city/infrared-skills
/plugin install infrared@infrared-skills
```

### Cursor

```text
/plugin marketplace add Infrared-city/infrared-skills
/plugin install infrared@infrared-skills
```

(Cursor 2.5+ uses the same plugin format as Claude Code; this repo ships both `.claude-plugin/` and `.cursor-plugin/` manifests.)

### Codex CLI / GitHub Copilot / Windsurf

These read `AGENTS.md` from the project root. Either clone this repo into your workspace, or copy the `plugins/infrared/skills/use-infrared/` folder into your project's `.agents/skills/` directory.

## Layout

- `plugins/infrared/skills/use-infrared/` — the skill (SKILL.md router + references)
- `AGENTS.md` — for Codex / Copilot / Windsurf

## License

Apache-2.0
