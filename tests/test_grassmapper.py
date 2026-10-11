import pytest
import sqlite3
import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr("grassmapper.DATA_DIR", tmp_path)
    monkeypatch.setattr("grassmapper.DB_PATH", tmp_path / "journal.db")
    import grassmapper
    grassmapper.init_db()
    yield tmp_path / "journal.db"


def test_init_db(tmp_db):
    conn = sqlite3.connect(tmp_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "hikes" in tables
    assert "observations" in tables
    assert "streaks" in tables
    conn.close()


def test_log_hike_and_retrieve(tmp_db):
    import grassmapper
    grassmapper._log_hike(
        trail_name="Test Peak",
        location="Test Valley",
        distance_km=8.5,
        difficulty="moderate",
        duration_min=120,
        notes="Beautiful views",
        mood="great",
        weather="sunny",
    )
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT * FROM hikes WHERE trail_name = 'Test Peak'").fetchone()
    assert row is not None
    assert row[2] == "Test Peak"  # trail_name
    assert row[4] == 8.5           # distance_km
    conn.close()


def test_streak_calculation(tmp_db, monkeypatch):
    import grassmapper
    conn = sqlite3.connect(tmp_db)
    today = datetime.date.today()
    for i in range(3):
        d = (today - datetime.timedelta(days=i)).isoformat()
        conn.execute("INSERT INTO streaks (date, activity, minutes) VALUES (?, 'hike', 60)", (d,))
    conn.commit()
    conn.close()

    grassmapper._print_streak()


def test_search_trails_no_key():
    import grassmapper
    with patch.object(grassmapper, "SERPAPI_KEY", ""):
        result = grassmapper.search_trails("Blue Ridge trail conditions")
    assert result == ""



def test_get_nature_fact_returns_string():
    import grassmapper
    result = grassmapper.get_nature_fact("red-tailed hawk")
    assert isinstance(result, str)
    assert len(result) > 0


def test_load_config_defaults(tmp_path, monkeypatch):
    import grassmapper
    monkeypatch.setattr("grassmapper.CONFIG_PATH", tmp_path / "config.json")
    cfg = grassmapper.load_config()
    assert cfg["model"] == grassmapper.DEFAULT_MODEL
    assert "units" in cfg


def test_save_and_load_config(tmp_path, monkeypatch):
    import grassmapper
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr("grassmapper.CONFIG_PATH", cfg_path)
    monkeypatch.setattr("grassmapper.DATA_DIR", tmp_path)

    grassmapper.save_config({"model": "llama3.2", "units": "imperial"})
    loaded = grassmapper.load_config()
    assert loaded["model"] == "llama3.2"
    assert loaded["units"] == "imperial"


@patch("grassmapper.ollama")
def test_check_ollama_success(mock_ollama):
    import grassmapper
    mock_ollama.list.return_value = MagicMock()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("grassmapper.OLLAMA_AVAILABLE", True)
    result = grassmapper.check_ollama()
    assert result is True
    monkeypatch.undo()


@patch("grassmapper.ollama")
def test_check_ollama_failure(mock_ollama):
    import grassmapper
    mock_ollama.list.side_effect = ConnectionRefusedError("not running")
    with patch.object(grassmapper, "OLLAMA_AVAILABLE", True):
        result = grassmapper.check_ollama()
    assert result is False


def test_flask_web_endpoints(tmp_db, monkeypatch):
    import app
    app.app.config["TESTING"] = True
    client = app.app.test_client()

    res = client.get("/")
    assert res.status_code == 200
    assert b"GrassMapper" in res.data

    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.get_json()
    assert "total_hikes" in data

    post_res = client.post("/api/journal", json={
        "trail_name": "Web Test Trail",
        "location": "Ridge Park",
        "distance_km": 5.2,
        "difficulty": "easy"
    })
    assert post_res.status_code == 200
    assert post_res.get_json()["success"] is True

    get_res = client.get("/api/journal")
    assert get_res.status_code == 200
    hikes = get_res.get_json()
    assert len(hikes) >= 1
    assert hikes[0]["trail_name"] == "Web Test Trail"

