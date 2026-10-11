import os
import json
import datetime
import textwrap
from flask import Flask, render_template, request, jsonify, Response, stream_with_context

from grassmapper import (
    init_db,
    get_db,
    load_config,
    check_ollama,
    search_trails,
    _log_hike,
    DEFAULT_MODEL,
    SERPAPI_KEY,
    SENTRY_AVAILABLE,
    OLLAMA_AVAILABLE,
)

if OLLAMA_AVAILABLE:
    import ollama
if SENTRY_AVAILABLE:
    import sentry_sdk

app = Flask(__name__)
init_db()


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


@app.route("/")
def index():
    cfg = load_config()
    ollama_ok = check_ollama() if OLLAMA_AVAILABLE else False
    has_serpapi = bool(SERPAPI_KEY)
    has_sentry = bool(SENTRY_AVAILABLE)
    return render_template(
        "index.html",
        model=cfg.get("model", DEFAULT_MODEL),
        ollama_ok=ollama_ok,
        has_serpapi=has_serpapi,
        has_sentry=has_sentry,
    )


@app.route("/api/stats")
def api_stats():
    conn = get_db()
    total_hikes = conn.execute("SELECT COUNT(*) FROM hikes").fetchone()[0]
    total_km = conn.execute("SELECT SUM(distance_km) FROM hikes").fetchone()[0] or 0.0
    total_min = conn.execute("SELECT SUM(duration_min) FROM hikes").fetchone()[0] or 0
    total_obs = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

    fav = conn.execute(
        "SELECT trail_name, COUNT(*) as c FROM hikes GROUP BY trail_name ORDER BY c DESC LIMIT 1"
    ).fetchone()

    dates = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT date FROM streaks ORDER BY date DESC"
        ).fetchall()
    ]
    conn.close()

    streak = 0
    today = datetime.date.today()
    for i, d in enumerate(dates):
        expected = (today - datetime.timedelta(days=i)).isoformat()
        if d == expected:
            streak += 1
        else:
            break

    return jsonify(
        {
            "total_hikes": total_hikes,
            "total_km": round(total_km, 1),
            "total_hours": round(total_min / 60.0, 1),
            "total_observations": total_obs,
            "streak": streak,
            "favorite_trail": fav[0] if fav else "None yet",
        }
    )


@app.route("/api/journal", methods=["GET", "POST"])
def api_journal():
    if request.method == "POST":
        data = request.json or {}
        trail_name = data.get("trail_name", "").strip()
        if not trail_name:
            return jsonify({"error": "Trail name is required"}), 400

        location = data.get("location", "")
        distance_km = float(data.get("distance_km", 0)) if data.get("distance_km") else None
        difficulty = data.get("difficulty", "moderate")
        duration_min = int(data.get("duration_min", 0)) if data.get("duration_min") else None
        notes = data.get("notes", "")
        mood = data.get("mood", "good")
        weather = data.get("weather", "")

        _log_hike(
            trail_name=trail_name,
            location=location,
            distance_km=distance_km,
            difficulty=difficulty,
            duration_min=duration_min,
            notes=notes,
            mood=mood,
            weather=weather,
        )

        today = datetime.date.today().isoformat()
        conn = get_db()
        conn.execute(
            "INSERT OR REPLACE INTO streaks (date, activity, minutes) VALUES (?, ?, ?)",
            (today, "hike", duration_min or 0),
        )
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": f"Saved {trail_name}!"})

    conn = get_db()
    hikes = conn.execute(
        """SELECT id, date, trail_name, location, distance_km, difficulty, duration_min, notes, mood, weather
           FROM hikes ORDER BY date DESC, id DESC LIMIT 50"""
    ).fetchall()

    result = []
    for h in hikes:
        hid, date, trail, loc, dist, diff, dur, notes, mood, weather = h
        obs = conn.execute(
            "SELECT category, name, description, ai_info FROM observations WHERE hike_id = ?",
            (hid,),
        ).fetchall()
        result.append(
            {
                "id": hid,
                "date": date,
                "trail_name": trail,
                "location": loc,
                "distance_km": dist,
                "difficulty": diff,
                "duration_min": dur,
                "notes": notes,
                "mood": mood,
                "weather": weather,
                "observations": [
                    {"category": o[0], "name": o[1], "description": o[2], "ai_info": o[3]}
                    for o in obs
                ],
            }
        )
    conn.close()
    return jsonify(result)


@app.route("/api/observe", methods=["POST"])
def api_observe():
    data = request.json or {}
    category = data.get("category", "plant")
    name = data.get("name", "").strip()
    desc = data.get("description", "").strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400

    cfg = load_config()
    model = cfg.get("model", DEFAULT_MODEL)
    ai_info = ""

    if OLLAMA_AVAILABLE and check_ollama():
        messages = [
            {
                "role": "system",
                "content": (
                    "You are GrassMapper's expert naturalist educator. Give a brief, "
                    "captivating (2-3 sentences) fact about this species. Include ecology or folklore."
                ),
            },
            {"role": "user", "content": f"Tell me about: {name} ({category}). Description: {desc}"},
        ]
        try:
            resp = ollama.chat(model=model, messages=messages)
            ai_info = resp.message.content
        except Exception as e:
            ai_info = f"Nature note generated offline. ({e})"

    today = datetime.date.today().isoformat()
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

    return jsonify({"success": True, "name": name, "category": category, "ai_info": ai_info})


@app.route("/api/plan", methods=["POST"])
def api_plan():
    data = request.json or {}
    region = data.get("region", "Blue Ridge, VA").strip()
    difficulty = data.get("difficulty", "moderate")
    distance = data.get("distance", "")
    interests = data.get("interests", "birds, waterfalls, trees")
    duration = data.get("duration", "half day")

    cfg = load_config()
    model = cfg.get("model", DEFAULT_MODEL)

    live_context = ""
    if SERPAPI_KEY:
        query = f"{region} hiking trails {difficulty} {interests} trail conditions {datetime.date.today().strftime('%B %Y')}"
        live_context = search_trails(query)

    grounding_block = (
        f"\n\nLIVE SEARCH RESULTS (from SerpApi — use this to ground real trails and conditions):\n{live_context}"
        if live_context
        else ""
    )

    system_prompt = textwrap.dedent(f"""
        You are GrassMapper, an enthusiastic trail guide and outdoor educator.
        Your goal is to get people off screens and into the wild.
        Format your response cleanly in Markdown.
        Include:
        # Trail Name & Location
        - **Distance & Difficulty:** [Stats]
        - **Estimated Time:** [Hours]
        ## Trail Highlights
        - What to see (focus on: {interests})
        ## Packing Checklist
        - What to bring
        ## Nature Facts & Wildlife to Spot
        - 2-3 fascinating facts about local plants or birds in this region.{grounding_block}
    """).strip()

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Plan a {difficulty} hike in {region}. "
                f"{'Distance: ~' + distance + ' km. ' if distance else ''}"
                f"Time available: {duration}. Interests: {interests}. "
                f"Date: {datetime.date.today().strftime('%B %d, %Y')}."
            ),
        },
    ]

    def generate():
        if not OLLAMA_AVAILABLE or not check_ollama():
            yield "data: Error: Ollama is not running. Please start Ollama locally.\n\n"
            return

        span = None
        if SENTRY_AVAILABLE:
            span = sentry_sdk.start_span(op="ai.inference", name=f"ollama/{model}/web_plan")
        try:
            stream = ollama.chat(model=model, messages=messages, stream=True)
            for chunk in stream:
                content = chunk.message.content or ""
                if content:
                    yield f"data: {json.dumps({'token': content})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if span:
                span.finish()

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json or {}
    user_msg = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    cfg = load_config()
    model = cfg.get("model", DEFAULT_MODEL)

    system_prompt = (
        "You are GrassMapper, an encouraging naturalist outdoor guide. "
        "Answer questions about hiking, plants, birds, trail safety, and geology. "
        "Keep responses engaging, helpful, and concise so people can get off the screen and outdoors!"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-6:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": user_msg})

    def generate():
        if not OLLAMA_AVAILABLE or not check_ollama():
            yield f"data: {json.dumps({'token': 'Ollama is not running. Start it to chat!'})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        try:
            stream = ollama.chat(model=model, messages=messages, stream=True)
            for chunk in stream:
                content = chunk.message.content or ""
                if content:
                    yield f"data: {json.dumps({'token': content})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


def main():
    port = int(os.environ.get("PORT", 5000))
    print(f"\n🌿 GrassMapper Web Dashboard starting at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
