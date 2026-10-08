<p align="center">
  <a href="https://infrared.city/">
    <img src="docs/assets/header.svg" alt="Infrared Skills: agent skill and cookbook for the Infrared SDK" />
  </a>
</p>

<p align="center">
  <a href="https://infrared.city/"><b>infrared.city</b></a> &nbsp;·&nbsp;
  <a href="https://infrared.city/docs/sdk/">SDK docs</a> &nbsp;·&nbsp;
  <a href="#install-the-plugin">Install</a> &nbsp;·&nbsp;
  <a href="#what-do-you-want-to-build">Router</a> &nbsp;·&nbsp;
  <a href="#cookbook">Cookbook</a>
</p>

---

## What this is

Tools to build with the [Infrared SDK](https://infrared.city/docs/sdk/) (urban microclimate: wind, sun, daylight, thermal comfort).

1. An **agent skill** (`use-infrared`). It teaches your coding agent the SDK in Python and TypeScript, for scripts, web apps, and Grasshopper.
2. A **cookbook**. Notebooks, scripts, and small apps. Each one answers one question about a real site.

The skill links to the docs site for API detail. It does not copy it.

## Install the plugin

**Claude Code** and **Cursor**:

```text
/plugin marketplace add Infrared-city/infrared-skills
/plugin install infrared@infrared-skills
```

**Codex CLI, GitHub Copilot, Windsurf**: these read [`AGENTS.md`](AGENTS.md). Clone this repo into your workspace. Or copy `plugins/infrared/skills/use-infrared/` into your project's `.agents/skills/` folder.

Get an API key at <https://infrared.city>. Set it as `INFRARED_API_KEY`. Never put it in code.

## What do you want to build?

| Goal | SDK | Go to |
|---|---|---|
| Grasshopper or Rhino component | Python in Rhino 8 | [grasshopper](plugins/infrared/skills/use-infrared/references/recipes/grasshopper.md), [geometry and drawing](plugins/infrared/skills/use-infrared/references/recipes/grasshopper-geometry-and-drawing.md), [pitfalls](plugins/infrared/skills/use-infrared/references/recipes/grasshopper-pitfalls.md) |
| Analysis, study or notebook for yourself | Python | [python/quickstart](plugins/infrared/skills/use-infrared/references/python/quickstart.md), [00_quickstart](cookbook/notebooks/00_quickstart.ipynb) |
| Web app for yourself (browser, map, 3D facades) | TypeScript in the browser | [typescript/quickstart](plugins/infrared/skills/use-infrared/references/typescript/quickstart.md), [map-grid](plugins/infrared/skills/use-infrared/references/typescript/map-grid.md), [facades-3d](plugins/infrared/skills/use-infrared/references/typescript/facades-3d.md), [apps/map-grid](cookbook/apps/map-grid), [apps/facades-3d](cookbook/apps/facades-3d) |
| Web app for many users (sign-in, secret key) | TypeScript front end + Cloudflare Worker proxy | [cloudflare-proxy](plugins/infrared/skills/use-infrared/references/typescript/cloudflare-proxy.md), [apps/cloudflare-proxy](cookbook/apps/cloudflare-proxy), [persistence-and-users](plugins/infrared/skills/use-infrared/references/recipes/persistence-and-users.md) |
| High-throughput backend (many sites, queue, cache) | Python service | [python-fastapi-app](plugins/infrared/skills/use-infrared/references/recipes/python-fastapi-app.md), [apps/python-fastapi](cookbook/apps/python-fastapi) |
| SketchUp or other CAD plugin | Ruby or Python, same API | [sketchup-plugin](plugins/infrared/skills/use-infrared/references/recipes/sketchup-plugin.md) |
| Upload your own data to the platform (no code) | none | [platform-byo-upload](plugins/infrared/skills/use-infrared/references/platform-byo-upload.md) |

## Cookbook

Each notebook uses your own model first. Public data (Overture) is the fallback. Preview a run before you send it: the preview is free.

| | |
|---|---|
| [![Sky view factor in HafenCity, Hamburg](docs/assets/cookbook/hafencity-svf.jpg)](cookbook/notebooks/00_quickstart.ipynb) | [![Four design variants compared on thermal comfort, Vienna](docs/assets/cookbook/vienna-variants-utci.jpg)](cookbook/notebooks/01_design_variants.ipynb) |
| **00 quickstart**: sky view factor on a basemap | **01 design variants**: four scenarios compared on thermal comfort |
| [![Pedestrian wind comfort in Midtown Manhattan](docs/assets/cookbook/midtown-wind-comfort.jpg)](cookbook/notebooks/03_wind_comfort.ipynb) | [![Summer sun on facades in 3D, Vienna](docs/assets/cookbook/karlsplatz-facades-3d.jpg)](cookbook/notebooks/04_solar_facades_3d.ipynb) |
| **03 wind comfort**: Lawson classes for a dense area | **04 solar facades 3D**: summer sun on every wall |
| [![Web app: result grid on a map](docs/assets/cookbook/app-map-grid.jpg)](cookbook/apps/map-grid) | [![Web app: facades in 3D with three.js](docs/assets/cookbook/app-facades-3d.jpg)](cookbook/apps/facades-3d) |
| **apps/map-grid**: draw an area, press Run, see the map | **apps/facades-3d**: facades and roofs in 3D in the browser |

- [`cookbook/notebooks/`](cookbook/notebooks/): nine case studies, 00 to 08.
- [`cookbook/scripts/`](cookbook/scripts/): three short Python scripts.
- [`cookbook/apps/`](cookbook/apps/): runnable web apps and a Python backend.
- [`cookbook/sample-data/`](cookbook/sample-data/): GeoJSON models for the examples.

See [`cookbook/README.md`](cookbook/README.md) for how to run them.

## Docs for agents

- Guide: <https://infrared.city/docs/sdk/>
- The whole guide as one Markdown file: <https://infrared.city/docs/sdk/sdk.md>
- Page index: <https://infrared.city/docs/sdk/llms.txt> and <https://infrared.city/docs/sdk/1.0/llms.txt>
- Each page also exists as Markdown: add `index.md` to its URL.

## Compatibility

| Plugin | Python SDK | TypeScript SDK | Branch |
|---|---|---|---|
| 1.0.x | `infrared-sdk` 1.0.x | `@infrared-city/infrared-sdk-ts` 1.0.x | `main` |
| 0.3.x | `infrared-sdk` 0.5.x | none | `sdk-0.5.x` (tag `sdk-0.5.x-final`, frozen) |

## Layout

```
infrared-skills/
├── plugins/infrared/skills/use-infrared/   # the agent skill (SKILL.md + references/)
├── cookbook/                               # notebooks, scripts, apps, sample data
├── AGENTS.md                               # for Codex, Copilot, Windsurf
└── docs/assets/                            # README artwork
```

## License

Apache-2.0. See [`LICENSE`](LICENSE).
