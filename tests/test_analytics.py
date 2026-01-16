import os
import io
import json
import tempfile
from pathlib import Path

def setup_db(tmp_path):
    from chat_db import ChatDatabase
    db_path = tmp_path / "chats.sqlite3"
    db = ChatDatabase(db_path)
    # Seed one chat with two messages and a tag
    cid = "test_chat_1"
    db.create_chat(cid, "Test Chat", model=None, budget_usd=1.0, tags=["demo"]) 
    db.add_message(cid, "user", "Hello", model=None)
    db.add_message(cid, "assistant", "Hi there", model="gpt-4o-mini")
    return db_path

def write_usage_log(path: Path, cid: str):
    content = (
        "timestamp_iso,model,input_tokens,output_tokens,cost_input_usd,cost_output_usd,cost_total_usd,prompt,chat_id\n"
        "2025-10-30T12:00:00,gpt-4o-mini,10,20,0.0001,0.0002,0.0003,Hello,{}\n".format(cid)
    )
    path.write_text(content, encoding="utf-8")

def test_analytics_usage_smoke(tmp_path, monkeypatch):
    # Arrange
    db_path = setup_db(tmp_path)
    usage_path = tmp_path / "usage_log.csv"
    write_usage_log(usage_path, "test_chat_1")

    import app as app_module
    app = app_module.app
    # Point settings to temp paths
    app_module.settings.use_sqlite_chats = True
    app_module.settings.chat_db_path = db_path
    app_module.settings.usage_log_path = usage_path

    # Act
    client = app.test_client()
    resp = client.get("/analytics/usage")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "total_chats" in data
    assert "total_messages" in data
    assert "model_mix" in data

def test_analytics_daily_smoke(tmp_path, monkeypatch):
    # Arrange
    db_path = setup_db(tmp_path)
    usage_path = tmp_path / "usage_log.csv"
    write_usage_log(usage_path, "test_chat_1")

    import app as app_module
    app = app_module.app
    app_module.settings.use_sqlite_chats = True
    app_module.settings.chat_db_path = db_path
    app_module.settings.usage_log_path = usage_path

    # Act
    client = app.test_client()
    resp = client.get("/analytics/daily")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "daily" in data
    # At least one row either from DB or usage log
    assert isinstance(data["daily"], list)

