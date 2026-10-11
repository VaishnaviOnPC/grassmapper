#!/usr/bin/env python3

import os
import sys
import json
import sqlite3
import datetime
import textwrap
import argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    import sentry_sdk
    SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
    if SENTRY_DSN:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )
    SENTRY_AVAILABLE = bool(SENTRY_DSN)
except ImportError:
    SENTRY_AVAILABLE = False

DATA_DIR = Path.home() / ".grassmapper"
DB_PATH = DATA_DIR / "journal.db"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_MODEL = "gemma3"
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

BANNER = r"""
  ___  ____  __   ____  ____  __  __   __   ____  ____  ____  ____
 / __)(  _ \/ _\ / ___)/ ___)(  \/  ) / _\ (  _ \(  _ \(  __)(  _ \
( (_ \ )   /    \\___ \\___ \ )    / /    \ ) __/ ) __/ ) _)  )   /
 \___/(__\_)\_/\_/(____/(____/(__/\_) \_/\_/(__)  (__)  (____)(__\_)

           🥾  Your Offline Hiking Companion  🌿
           Powered by Gemma 3 (open-weight) via Ollama
"""

COLORS = {
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "blue":   "\033[94m",
    "cyan":   "\033[96m",
    "red":    "\033[91m",
    "bold":   "\033[1m",
    "reset":  "\033[0m",
    "dim":    "\033[2m",
}

def c(text: str, color: str) -> str:
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS hikes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            trail_name  TEXT    NOT NULL,
            location    TEXT,
            distance_km REAL,
            difficulty  TEXT,
            duration_min INTEGER,
            notes       TEXT,
            mood        TEXT,
            weather     TEXT,
            created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS observations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hike_id     INTEGER REFERENCES hikes(id),
            date        TEXT    NOT NULL,
            category    TEXT,   -- plant / bird / insect / geology / other
            name        TEXT,
            description TEXT,
            ai_info     TEXT,
            created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS streaks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    UNIQUE NOT NULL,
            activity    TEXT,
            minutes     INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


def get_db():
    return sqlite3.connect(DB_PATH)


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"model": DEFAULT_MODEL, "units": "metric"}


def save_config(cfg: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def check_ollama() -> bool:
    if not OLLAMA_AVAILABLE:
        print(c("⚠  ollama Python package not installed. Run: pip install ollama", "yellow"))
        return False
    try:
        ollama.list()
        return True
    except Exception:
        print(c("⚠  Ollama server not running. Start it with: ollama serve", "yellow"))
        return False


def stream_ai(messages: list, model: str) -> str:
    span = None
    if SENTRY_AVAILABLE:
        span = sentry_sdk.start_span(op="ai.inference", name=f"ollama/{model}")
    try:
        response = ollama.chat(model=model, messages=messages, stream=True)
        full_text = ""
        print(c("🤖 GrassMapper AI: ", "green"), end="", flush=True)
        for chunk in response:
            token = chunk.message.content or ""
            print(token, end="", flush=True)
            full_text += token
        print()
        return full_text
    finally:
        if span:
            span.finish()


simple_stream = stream_ai


def search_trails(query: str) -> str:
    if not SERPAPI_KEY or not REQUESTS_AVAILABLE:
        return ""

    span = None
    if SENTRY_AVAILABLE:
        span = sentry_sdk.start_span(op="tool.search", name="serpapi/search_trails")
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": SERPAPI_KEY, "num": 5},
            timeout=10,
        )
        data = resp.json()
        results = data.get("organic_results", [])[:3]
        if not results:
            return ""
        lines = []
        for r in results:
            lines.append(f"• {r.get('title', '')}: {r.get('snippet', '')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"
    finally:
        if span:
            span.finish()


def get_nature_fact(species: str) -> str:
    return f"Generating nature facts about '{species}' from model knowledge."


def cmd_plan(args):
    cfg = load_config()
    model = cfg["model"]

    if not check_ollama():
        return

    print(c("\n🗺  Trail Planner", "cyan") + c(f" — {model} (local/offline)", "dim"))
    print(c("─" * 50, "dim"))

    region     = input(c("Region / area (e.g. 'Blue Ridge, VA'): ", "yellow")).strip() or "any"
    difficulty = input(c("Difficulty [easy/moderate/hard]: ", "yellow")).strip() or "moderate"
    distance   = input(c("Target distance in km (or press Enter to skip): ", "yellow")).strip()
    interests  = input(c("Interests (e.g. 'waterfalls, fall foliage, birds'): ", "yellow")).strip()
    duration   = input(c("Available time (e.g. 'half day', '3 hours'): ", "yellow")).strip() or "half day"

    live_context = ""
    if SERPAPI_KEY:
        search_query = (
            f"{region} hiking trails {difficulty} {interests} "
            f"trail conditions {datetime.date.today().strftime('%B %Y')}"
        )
        print(c("\n🔍 Fetching live trail info via SerpApi...", "dim"))
        live_context = search_trails(search_query)
        if live_context:
            print(c("✓ Live trail data fetched — grounding AI response.\n", "dim"))
        else:
            print(c("⚠  No live results returned — using model knowledge only.\n", "dim"))
    else:
        print(c("ℹ  No SERPAPI_KEY — using offline model knowledge.\n", "dim"))

    grounding_block = (
        f"\n\nLIVE TRAIL DATA (fetched from SerpApi — use this to ground your response):\n{live_context}"
        if live_context else ""
    )

    system_prompt = textwrap.dedent(f"""
        You are GrassMapper, an expert trail guide and outdoor educator.
        Your goal is to get people off screens and into nature.
        Always be enthusiastic, specific, and practical.
        Provide a structured trail plan with:
        1. Trail name and location
        2. Distance and elevation gain
        3. Key highlights and what to look for (especially birds/wildlife if requested)
        4. Best time of day / season tips
        5. What to bring checklist
        6. 2-3 fascinating nature facts relevant to the area{grounding_block}
    """).strip()

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Plan a {difficulty} hike in {region}. "
                f"{'Distance: ~' + distance + ' km. ' if distance else ''}"
                f"Time available: {duration}. "
                f"My interests: {interests or 'general nature'}. "
                f"Today's date: {datetime.date.today().strftime('%B %d, %Y')}."
            ),
        },
    ]

    print(c("⏳ Generating your trail plan...\n", "dim"))
    stream_ai(messages, model)

    save = input(c("\n💾 Save this plan to your journal? [y/N]: ", "yellow")).strip().lower()
    if save == "y":
        trail_name = input(c("Trail name: ", "yellow")).strip() or "Planned Trail"
        _log_hike(trail_name, region, distance or None, difficulty)


def _log_hike(trail_name, location, distance_km, difficulty, duration_min=None, notes="", mood="", weather=""):
    conn = get_db()
    conn.execute(
        """INSERT INTO hikes (date, trail_name, location, distance_km, difficulty, duration_min, notes, mood, weather)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.date.today().isoformat(),
            trail_name, location,
            float(distance_km) if distance_km else None,
            difficulty, duration_min, notes, mood, weather,
        ),
    )
    conn.commit()
    conn.close()
    print(c(f"✅ Hike '{trail_name}' saved to your journal!", "green"))


def cmd_log(args):
    print(c("\n📓 Log a Hike", "cyan"))
    print(c("─" * 50, "dim"))

    trail_name   = input(c("Trail name: ", "yellow")).strip()
    if not trail_name:
        print(c("Trail name is required.", "red"))
        return

    location     = input(c("Location (city/region): ", "yellow")).strip()
    distance     = input(c("Distance in km: ", "yellow")).strip()
    difficulty   = input(c("Difficulty [easy/moderate/hard]: ", "yellow")).strip() or "moderate"
    duration     = input(c("Duration in minutes: ", "yellow")).strip()
    weather      = input(c("Weather conditions: ", "yellow")).strip()
    mood         = input(c("How did it feel? [great/good/okay/tough]: ", "yellow")).strip()
    notes        = input(c("Notes / highlights (press Enter to skip): ", "yellow")).strip()

    _log_hike(
        trail_name, location,
        distance or None, difficulty,
        int(duration) if duration else None,
        notes, mood, weather,
    )

    today = datetime.date.today().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO streaks (date, activity, minutes) VALUES (?, ?, ?)",
        (today, "hike", int(duration) if duration else 0),
    )
    conn.commit()
    conn.close()

    obs = input(c("\n🌿 Log a nature observation from this hike? [y/N]: ", "yellow")).strip().lower()
    if obs == "y":
        cmd_observe(args, hike_date=today)


def cmd_observe(args, hike_date: str = None):
    cfg = load_config()
    print(c("\n🌿 Nature Observation", "cyan"))
    print(c("─" * 50, "dim"))

    category = input(c("Category [plant/bird/insect/geology/other]: ", "yellow")).strip() or "other"
    name     = input(c("Name (common or scientific): ", "yellow")).strip()
    desc     = input(c("Describe what you saw: ", "yellow")).strip()

    ai_info = ""
    if name and check_ollama():
        model = cfg["model"]
        print(c(f"\n🤖 Getting AI info about '{name}'...", "dim"))
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a naturalist educator. Give a brief (3-4 sentence) "
                    "fascinating fact about the species mentioned. Include ecology, "
                    "behavior, or folklore. Be concise and engaging."
                ),
            },
            {"role": "user", "content": f"Tell me about: {name} ({category}). Description: {desc}"},
        ]
        ai_info = stream_ai(messages, model)

    today = hike_date or datetime.date.today().isoformat()
    conn = get_db()
    hike_id = conn.execute(
        "SELECT id FROM hikes WHERE date = ? ORDER BY id DESC LIMIT 1", (today,)
    ).fetchone()
    conn.execute(
        """INSERT INTO observations (hike_id, date, category, name, description, ai_info)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (hike_id[0] if hike_id else None, today, category, name, desc, ai_info),
    )
    conn.commit()
    conn.close()
    print(c(f"✅ Observation '{name}' saved!", "green"))

    another = input(c("\nLog another observation? [y/N]: ", "yellow")).strip().lower()
    if another == "y":
        cmd_observe(args, hike_date=hike_date)


def cmd_journal(args):
    conn = get_db()
    limit = getattr(args, "limit", 10)

    print(c("\n📖 Your Outdoor Journal", "cyan"))
    print(c("─" * 60, "dim"))

    hikes = conn.execute(
        "SELECT id, date, trail_name, location, distance_km, difficulty, duration_min, mood, notes "
        "FROM hikes ORDER BY date DESC LIMIT ?",
        (limit,),
    ).fetchall()

    if not hikes:
        print(c("No hikes logged yet. Use 'grassmapper log' to record your first hike!", "yellow"))
        conn.close()
        return

    for h in hikes:
        hid, date, trail, loc, dist, diff, dur, mood, notes = h
        dist_str = f"{dist:.1f} km" if dist else "?"
        dur_str  = f"{dur} min"     if dur  else "?"
        mood_icon = {"great": "😄", "good": "🙂", "okay": "😐", "tough": "😓"}.get(mood, "🥾")
        print(f"\n{c(date, 'bold')} {mood_icon}  {c(trail, 'green')}")
        print(f"  📍 {loc or 'unknown'} | 📏 {dist_str} | ⏱ {dur_str} | 💪 {diff or '?'}")
        if notes:
            print(c(f"  📝 {notes[:120]}", "dim"))

        obs = conn.execute(
            "SELECT category, name FROM observations WHERE hike_id = ?", (hid,)
        ).fetchall()
        if obs:
            obs_str = ", ".join(f"{cat}: {nm}" for cat, nm in obs)
            print(c(f"  🌿 Observations: {obs_str}", "cyan"))

    conn.close()
    _print_streak()


def _print_streak():
    conn = get_db()
    dates = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM streaks ORDER BY date DESC"
        ).fetchall()
    ]
    conn.close()

    if not dates:
        return

    streak = 0
    today = datetime.date.today()
    for i, d in enumerate(dates):
        expected = (today - datetime.timedelta(days=i)).isoformat()
        if d == expected:
            streak += 1
        else:
            break

    if streak > 0:
        fire = "🔥" * min(streak, 5)
        print(c(f"\n  {fire}  Current outdoor streak: {streak} day(s)!", "yellow"))

def cmd_chat(args):
    cfg = load_config()
    model = cfg["model"]

    if not check_ollama():
        return

    print(c("\n🌲 Nature Chat", "cyan") + c(f" — model: {model} (local)", "dim"))
    print(c("Type your question. Enter 'quit' to exit.\n", "dim"))

    system_prompt = (
        "You are GrassMapper, an enthusiastic naturalist and hiking guide. "
        "Answer questions about plants, wildlife, trail safety, foraging, and ecology. "
        "Keep answers engaging and encourage the user to get outside!"
    )
    messages = [{"role": "system", "content": system_prompt}]

    while True:
        try:
            user_input = input(c("\nYou: ", "bold")).strip()
        except (KeyboardInterrupt, EOFError):
            print(c("\n\nGo touch grass! 🌿", "green"))
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print(c("\nHappy trails! 🥾", "green"))
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        reply = stream_ai(messages, model)
        messages.append({"role": "assistant", "content": reply})


def cmd_stats(args):
    conn = get_db()

    total_hikes = conn.execute("SELECT COUNT(*) FROM hikes").fetchone()[0]
    total_km    = conn.execute("SELECT SUM(distance_km) FROM hikes").fetchone()[0] or 0
    total_min   = conn.execute("SELECT SUM(duration_min) FROM hikes").fetchone()[0] or 0
    total_obs   = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

    fav = conn.execute(
        "SELECT trail_name, COUNT(*) as c FROM hikes GROUP BY trail_name ORDER BY c DESC LIMIT 1"
    ).fetchone()

    month = datetime.date.today().strftime("%Y-%m")
    this_month = conn.execute(
        "SELECT COUNT(*) FROM hikes WHERE date LIKE ?", (f"{month}%",)
    ).fetchone()[0]

    conn.close()

    print(c("\n📊 Your Outdoor Stats", "cyan"))
    print(c("─" * 40, "dim"))
    print(f"  🥾 Total hikes logged:   {c(str(total_hikes), 'green')}")
    print(f"  📏 Total distance:       {c(f'{total_km:.1f} km', 'green')}")
    print(f"  ⏱  Total time outside:   {c(f'{total_min // 60}h {total_min % 60}m', 'green')}")
    print(f"  🌿 Nature observations:  {c(str(total_obs), 'green')}")
    print(f"  📅 Hikes this month:     {c(str(this_month), 'green')}")
    if fav:
        print(f"  ❤️  Favourite trail:     {c(fav[0], 'green')} ({fav[1]}x)")
    _print_streak()


def cmd_config(args):
    cfg = load_config()
    print(c("\n⚙️  GrassMapper Config", "cyan"))
    print(f"  Current model: {c(cfg['model'], 'green')}")
    print(f"  Units:         {c(cfg['units'], 'green')}")
    print()

    if check_ollama():
        try:
            models = [m.model for m in ollama.list().models]
            print(c("Available Ollama models:", "dim"))
            for m in models:
                marker = " ✓" if m == cfg["model"] else ""
                print(f"    {m}{c(marker, 'green')}")
        except Exception:
            pass

    new_model = input(c(f"\nNew model (Enter to keep '{cfg['model']}'): ", "yellow")).strip()
    if new_model:
        cfg["model"] = new_model
        save_config(cfg)
        print(c(f"✅ Model set to: {new_model}", "green"))
    else:
        print(c("Config unchanged.", "dim"))


def cmd_challenge(args):
    cfg = load_config()
    model = cfg["model"]

    if not check_ollama():
        return

    conn = get_db()
    recent_hikes = conn.execute(
        "SELECT trail_name, location, difficulty FROM hikes ORDER BY date DESC LIMIT 5"
    ).fetchall()
    conn.close()

    context = ""
    if recent_hikes:
        context = "My recent hikes: " + "; ".join(
            f"{t} ({loc}, {diff})" for t, loc, diff in recent_hikes
        )

    print(c("\n🎯 Outdoor Challenge Generator", "cyan"))
    print(c("─" * 50, "dim"))

    duration = input(c("Duration [week/month]: ", "yellow")).strip() or "week"
    focus    = input(c("Focus area (e.g. 'birds, night hikes, foraging'): ", "yellow")).strip()

    messages = [
        {
            "role": "system",
            "content": (
                "You are GrassMapper, an outdoor challenge coach. "
                "Generate creative, achievable outdoor challenges that get people off screens. "
                "Make them specific, measurable, and fun. Include a mix of easy wins and stretch goals."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Create a {duration} outdoor challenge for me. "
                f"Focus: {focus or 'general nature exploration'}. "
                f"{context}. "
                f"Today: {datetime.date.today().strftime('%B %d, %Y')}."
            ),
        },
    ]

    print(c("\n⏳ Generating your challenge...\n", "dim"))
    stream_ai(messages, model)


def cmd_web(args):
    import app
    app.main()


def main():
    # Fix Windows terminal encoding for emoji output
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    init_db()

    parser = argparse.ArgumentParser(
        prog="grassmapper",
        description="🥾 GrassMapper — Your offline AI hiking companion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Commands:
              web         Launch the modern Web Dashboard (browser UI)
              plan        Generate a personalized trail plan (AI-powered)
              log         Log a completed hike to your journal
              observe     Log a nature observation with AI enrichment
              journal     View your outdoor journal
              stats       Show your hiking stats and streak
              chat        Chat with your trail guide AI (ask anything nature)
              challenge   Get a personalized outdoor challenge
              config      Configure model and settings

            Environment variables:
              SERPAPI_KEY   Enable live trail/weather search (optional)
              SENTRY_DSN    Enable agent tracing (optional)
              OLLAMA_HOST   Custom Ollama host (default: localhost:11434)

            Examples:
              grassmapper web
              grassmapper plan
              grassmapper log
              grassmapper chat
              grassmapper journal --limit 20
              grassmapper stats
        """),
    )

    sub = parser.add_subparsers(dest="command")

    p_web = sub.add_parser("web", help="Launch the Web Dashboard UI")
    p_web.set_defaults(func=cmd_web)

    p_plan = sub.add_parser("plan", help="Generate a trail plan")
    p_plan.set_defaults(func=cmd_plan)

    p_log = sub.add_parser("log", help="Log a completed hike")
    p_log.set_defaults(func=cmd_log)

    p_obs = sub.add_parser("observe", help="Log a nature observation")
    p_obs.set_defaults(func=cmd_observe)

    p_journal = sub.add_parser("journal", help="View your journal")
    p_journal.add_argument("--limit", type=int, default=10, help="Number of entries to show")
    p_journal.set_defaults(func=cmd_journal)

    p_stats = sub.add_parser("stats", help="Show your stats")
    p_stats.set_defaults(func=cmd_stats)

    p_chat = sub.add_parser("chat", help="Chat with your trail guide AI")
    p_chat.set_defaults(func=cmd_chat)

    p_chal = sub.add_parser("challenge", help="Get a personalized outdoor challenge")
    p_chal.set_defaults(func=cmd_challenge)

    p_cfg = sub.add_parser("config", help="Configure GrassMapper")
    p_cfg.set_defaults(func=cmd_config)


    args = parser.parse_args()

    print(c(BANNER, "green"))

    if args.command is None:
        parser.print_help()
        print(c("\n💡 Tip: Run 'grassmapper plan' to generate your first trail plan!\n", "cyan"))
        return

    args.func(args)


if __name__ == "__main__":
    main()
