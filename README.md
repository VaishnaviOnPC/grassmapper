# 🥾 GrassMapper

> **Your offline AI hiking companion** — get off the screen and into the world.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![Powered by Gemma 3](https://img.shields.io/badge/AI-Gemma%203%20(open--weight)-green.svg)](https://ollama.com/library/gemma3)
[![Runs offline](https://img.shields.io/badge/runs-100%25%20offline-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

GrassMapper is a **fully offline**, privacy-first CLI app that uses the **Gemma 3** open-weight model (via Ollama) to:

- 🗺️ **Plan hikes** — AI-generated trail plans with highlights, what-to-bring lists, and nature trivia
- 📓 **Keep an outdoor journal** — log hikes with distance, mood, weather, and observations
- 🌿 **Enrich nature observations** — point at a plant or bird, get AI facts instantly
- 🎯 **Generate outdoor challenges** — personalized weekly/monthly nature goals
- 💬 **Chat with your trail guide** — ask anything about plants, birds, trails, gear
- 🔥 **Track your streak** — gamified outdoor habit tracking with daily streaks

**No API key required. No data leaves your laptop. Works in the backcountry.**

---

## Why Open-Source AI?

| Concern | Closed AI | GrassMapper (open-weight) |
|---|---|---|
| **Privacy** | Your hike data hits their servers | Everything stays on your machine |
| **Offline** | Needs internet | Works with zero connectivity |
| **Cost** | Per-token charges | Free forever after setup |
| **Swap models** | Locked in | Switch Gemma → Llama → Mistral in one command |
| **Fine-tune** | Not allowed | Fine-tune on your own trail data |

This is exactly where open innovation matters: a trail journal is deeply personal. Your data about where you hike, what you observe, and how you feel shouldn't live on a company's server. With open-weight models, you get state-of-the-art AI that fits in your pack.

---

## Quick Start

### 1. Install Ollama and pull Gemma 3

```bash
# Install Ollama: https://ollama.com
ollama pull gemma3
```

### 2. Install GrassMapper

```bash
pip install -e ".[sentry]"   # from this repo
# or
pip install ollama requests
python grassmapper.py --help
```

### 3. Launch the Web Dashboard or CLI

**Option A: Web Dashboard (Browser UI)**
```bash
python app.py
# or: grassmapper web
# Open http://localhost:5000 in your browser!
```

**Option B: Terminal CLI (Field & Backcountry)**
```bash
grassmapper plan
```

---

## All Commands

```bash
grassmapper web         # 🌐 Launch the modern Web Dashboard UI
grassmapper plan        # 🗺️ AI trail plan generator
grassmapper log         # 📓 Log a completed hike
grassmapper observe     # 🌿 Log a nature observation (AI-enriched)
grassmapper journal     # 📖 View your outdoor journal
grassmapper stats       # 📊 Hiking stats + streak
grassmapper chat        # 💬 Chat with your trail guide AI
grassmapper challenge   # 🎯 Get a weekly outdoor challenge
grassmapper config      # ⚙️ Change AI model, units, etc.
```

---

## Optional: Live Trail Search (SerpApi)

When you have internet, GrassMapper can fetch live trail conditions and weather:

```bash
export SERPAPI_KEY=your_key_here
grassmapper chat
# "What are the current trail conditions on the Appalachian Trail in Virginia?"
```

Without this key, everything runs 100% offline from the model's knowledge.

---

## Optional: Agent Tracing (Sentry)

```bash
export SENTRY_DSN=your_dsn_here
pip install "grassmapper[sentry]"
# All AI inference calls are now traced with latency + token counts
```

---

## Swapping Models

GrassMapper defaults to `gemma3` but you can use any Ollama model:

```bash
ollama pull llama3.2
grassmapper config
# → New model: llama3.2

# Or pull a vision model for image-based plant ID (future feature):
ollama pull llava
```

---

## Data Storage

All data is stored locally in `~/.grassmapper/`:
- `journal.db` — SQLite database with your hikes and observations
- `config.json` — model and unit preferences

No network required. No accounts. No telemetry.

## Deploying to Render (Best Use of Render Prize 🚀)

GrassMapper comes ready with a `render.yaml` blueprint:

1. Push your GrassMapper repository to GitHub.
2. In [Render Dashboard](https://dashboard.render.com/), click **New +** > **Blueprint**.
3. Select your repository. Render will automatically detect `render.yaml` and configure the Flask web service with Gunicorn!
4. (Optional) Set `SERPAPI_KEY` and `SENTRY_DSN` in Render's Environment variables.

---

## Tech Stack


| Component | Choice | Why open? |
|---|---|---|
| **AI model** | Gemma 3 (Google open-weight) | State-of-art, runs locally |
| **Inference** | Ollama | One-command local LLM server |
| **Language** | Python 3.10+ | Cross-platform, no build step |
| **Storage** | SQLite | Zero dependencies, works offline |
| **Live search** | SerpApi (optional) | Grounded real-world data |
| **Tracing** | Sentry (optional) | Open-source agent observability |

---

## License

MIT — fork it, fine-tune it, take it off-grid.

---

*Built for Hacktoberfest 2026 — Touch Grass Challenge* 🌿
