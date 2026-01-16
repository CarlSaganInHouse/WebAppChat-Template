"""Analytics routes blueprint for Flask application."""
import csv
import datetime
import os
from flask import Blueprint, request, jsonify
import structlog

from config import get_settings
from chat_db import get_chat_db

logger = structlog.get_logger()
analytics_bp = Blueprint('analytics', __name__)

# Get settings
settings = get_settings()


def _parse_date_yyyymmdd(s: str):
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _iter_usage_rows(start_date=None, end_date=None):
    """Yield rows from usage log CSV optionally filtered by date range (inclusive)."""
    path = settings.usage_log_path
    if not os.path.exists(path):
        return
    sd = _parse_date_yyyymmdd(start_date) if start_date else None
    ed = _parse_date_yyyymmdd(end_date) if end_date else None
    try:
        with open(path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                ts = (row.get("timestamp_iso") or "")[:10]
                if sd or ed:
                    try:
                        d = datetime.datetime.strptime(ts, "%Y-%m-%d").date()
                    except Exception:
                        continue
                    if sd and d < sd:
                        continue
                    if ed and d > ed:
                        continue
                yield row
    except FileNotFoundError:
        return


@analytics_bp.get("/analytics/usage")
def analytics_usage():
    """Overall usage statistics (requires SQLite chat storage)."""
    if not settings.use_sqlite_chats:
        return jsonify({"error": "analytics_requires_sqlite"}), 400

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    try:
        # DB-level stats
        db = get_chat_db(settings.chat_db_path)
        conn = db.get_conn()
        cur = conn.cursor()

        total_chats = cur.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
        total_messages = cur.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

        # Top tags (guard if table missing in older DBs)
        top_tags = []
        try:
            tags = cur.execute(
                "SELECT tag, COUNT(DISTINCT m.chat_id) AS chat_count, COUNT(m.id) AS message_count "
                "FROM chat_tags ct LEFT JOIN messages m ON m.chat_id=ct.chat_id "
                "GROUP BY tag ORDER BY message_count DESC LIMIT 5"
            ).fetchall()
            top_tags = [
                {"tag": t[0], "chat_count": t[1], "message_count": t[2]} for t in tags
            ]
        except Exception:
            top_tags = []

        # Model mix by assistant messages
        models = cur.execute(
            "SELECT COALESCE(model,'unknown') AS model, COUNT(*) FROM messages "
            "WHERE role='assistant' GROUP BY model ORDER BY COUNT(*) DESC"
        ).fetchall()
        model_mix = {m[0]: m[1] for m in models}

        # Chats over budget
        try:
            over = cur.execute(
                "SELECT id, title, budget_usd, spent_usd FROM chats "
                "WHERE budget_usd IS NOT NULL AND spent_usd IS NOT NULL AND spent_usd > budget_usd "
                "ORDER BY (spent_usd - budget_usd) DESC LIMIT 10"
            ).fetchall()
            chats_over_budget = [
                {
                    "id": r[0],
                    "title": r[1],
                    "budget_usd": r[2],
                    "spent_usd": r[3],
                    "over_by": round((r[3] or 0) - (r[2] or 0), 4),
                }
                for r in over
            ]
        except Exception:
            chats_over_budget = []
        conn.close()

        # CSV-level spend totals
        total_spend = 0.0
        for row in _iter_usage_rows(start_date, end_date):
            try:
                total_spend += float(row.get("cost_total_usd") or 0)
            except Exception:
                pass

        return jsonify(
            {
                "total_chats": total_chats,
                "total_messages": total_messages,
                "total_spend_usd": round(total_spend, 6),
                "top_tags": top_tags,
                "model_mix": model_mix,
                "chats_over_budget": chats_over_budget,
            }
        )
    except Exception as e:
        logger.error("analytics_failed", error=str(e))
        return jsonify({"error": "analytics_failed"}), 500


@analytics_bp.get("/analytics/tokens")
def analytics_tokens():
    """Token usage and costs grouped by model from usage log CSV."""
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    by_model = {}
    for row in _iter_usage_rows(start_date, end_date):
        m = row.get("model") or "unknown"
        d = by_model.setdefault(
            m, {"in_tokens": 0, "out_tokens": 0, "cost_usd": 0.0, "message_count": 0}
        )
        try:
            d["in_tokens"] += int(row.get("input_tokens") or 0)
            d["out_tokens"] += int(row.get("output_tokens") or 0)
            d["cost_usd"] += float(row.get("cost_total_usd") or 0)
            d["message_count"] += 1
        except Exception:
            continue

    # Round costs
    for v in by_model.values():
        v["cost_usd"] = round(v["cost_usd"], 6)

    return jsonify({"by_model": by_model})


@analytics_bp.get("/analytics/daily")
def analytics_daily():
    """Daily message counts (DB) and spend (CSV)."""
    if not settings.use_sqlite_chats:
        return jsonify({"error": "analytics_requires_sqlite"}), 400

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    try:
        # DB daily message stats
        db = get_chat_db(settings.chat_db_path)
        conn = db.get_conn()
        cur = conn.cursor()
        params = []
        where = []
        if start_date:
            where.append("timestamp >= strftime('%s', ?)")
            params.append(start_date)
        if end_date:
            # add one day to make inclusive end
            where.append("timestamp <= strftime('%s', ?)")
            params.append(end_date)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        rows = cur.execute(
            f"SELECT DATE(timestamp, 'unixepoch') as date, COUNT(*) as message_count, COUNT(DISTINCT chat_id) as chat_count "
            f"FROM messages{where_sql} GROUP BY DATE(timestamp, 'unixepoch') ORDER BY date ASC",
            params,
        ).fetchall()
        conn.close()
        daily = {
            r[0]: {
                "message_count": r[1],
                "chat_count": r[2],
                "tokens": 0,
                "cost_usd": 0.0,
            }
            for r in rows
        }

        # CSV daily spend + tokens
        for row in _iter_usage_rows(start_date, end_date):
            day = (row.get("timestamp_iso") or "")[:10]
            if not day:
                continue
            d = daily.setdefault(
                day, {"message_count": 0, "chat_count": 0, "tokens": 0, "cost_usd": 0.0}
            )
            try:
                d["tokens"] += int(row.get("input_tokens") or 0) + int(
                    row.get("output_tokens") or 0
                )
                d["cost_usd"] += float(row.get("cost_total_usd") or 0)
            except Exception:
                pass

        # Round costs
        out = [
            {
                "date": k,
                **{
                    "message_count": v["message_count"],
                    "chat_count": v["chat_count"],
                    "tokens": v["tokens"],
                    "cost_usd": round(v["cost_usd"], 6),
                },
            }
            for k, v in sorted(daily.items(), key=lambda x: x[0])
        ]
        return jsonify({"daily": out})
    except Exception as e:
        logger.error("analytics_failed", error=str(e))
        return jsonify({"error": "analytics_failed"}), 500


@analytics_bp.get("/analytics/tags")
def analytics_tags():
    """Usage breakdown by tag (counts from DB; tokens/cost from usage log by chat_id)."""
    if not settings.use_sqlite_chats:
        return jsonify({"error": "analytics_requires_sqlite"}), 400

    try:
        db = get_chat_db(settings.chat_db_path)
        conn = db.get_conn()
        cur = conn.cursor()
        # Tag counts
        tag_rows = cur.execute(
            "SELECT ct.tag, COUNT(DISTINCT m.chat_id) as chat_count, COUNT(m.id) as message_count "
            "FROM chat_tags ct JOIN messages m ON m.chat_id = ct.chat_id "
            "GROUP BY ct.tag"
        ).fetchall()
        # Map chat_id -> tags
        chat_tag_map = {}
        for row in cur.execute("SELECT chat_id, tag FROM chat_tags").fetchall():
            chat_tag_map.setdefault(row[0], set()).add(row[1])
        conn.close()

        # Aggregate tokens/cost per tag from usage log
        tag_stats = {
            t[0]: {
                "chat_count": t[1],
                "message_count": t[2],
                "tokens": 0,
                "cost_usd": 0.0,
            }
            for t in tag_rows
        }
        for row in _iter_usage_rows():
            cid = row.get("chat_id")
            if not cid:
                continue
            tags = chat_tag_map.get(cid)
            if not tags:
                continue
            try:
                tok = int(row.get("input_tokens") or 0) + int(
                    row.get("output_tokens") or 0
                )
                cost = float(row.get("cost_total_usd") or 0)
            except Exception:
                continue
            for tag in tags:
                d = tag_stats.get(tag)
                if d is None:
                    d = tag_stats[tag] = {
                        "chat_count": 0,
                        "message_count": 0,
                        "tokens": 0,
                        "cost_usd": 0.0,
                    }
                d["tokens"] += tok
                d["cost_usd"] += cost

        # Round costs
        for v in tag_stats.values():
            v["cost_usd"] = round(v["cost_usd"], 6)

        return jsonify({"by_tag": tag_stats})
    except Exception as e:
        logger.error("analytics_failed", error=str(e))
        return jsonify({"error": "analytics_failed"}), 500


@analytics_bp.get("/total-usage")
def total_usage():
    """Get total usage cost from usage log CSV."""
    total = 0.0
    try:
        with open(settings.usage_log_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    total += float(row.get("cost_total_usd") or 0)
                except:
                    pass
    except FileNotFoundError:
        pass
    return jsonify({"total_usd": round(total, 4)})
