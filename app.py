"""
Flask: прокси LiveScore API для РПЛ (`/api/livescore/rpl/*`).
Фронт: `football-stats/` (Vite проксирует `/api` → порт 5001).
"""
from pathlib import Path

try:
    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parent
    load_dotenv(_root / ".env")
    load_dotenv(_root / "football-stats" / ".env")
    load_dotenv(_root / "livescore.local.env", override=True)
    load_dotenv(_root / "football-stats" / "livescore.local.env", override=True)
except ImportError:
    pass

import logging

from flask import Flask, jsonify, request
from flask_cors import CORS

import livescore_api

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route("/api/livescore/rpl/live", methods=["GET"])
def livescore_rpl_live():
    try:
        matches, err = livescore_api.fetch_rpl_live_matches()
        if err:
            return jsonify({"error": err, "matches": matches or []}), 502
        return jsonify({"matches": matches})
    except Exception as e:
        logger.exception("livescore_rpl_live: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера", "matches": []}), 500


@app.route("/api/livescore/rpl/matches", methods=["GET"])
def livescore_rpl_matches():
    try:
        iso_date = request.args.get("date")
        if not iso_date:
            return jsonify({"error": "Укажите параметр date (YYYY-MM-DD).", "matches": []}), 400
        matches, err = livescore_api.fetch_rpl_matches_for_date(iso_date)
        if err:
            return jsonify({"error": err, "matches": matches or []}), 502
        return jsonify({"matches": matches})
    except Exception as e:
        logger.exception("livescore_rpl_matches: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера", "matches": []}), 500


@app.route("/api/livescore/rpl/standings", methods=["GET"])
def livescore_rpl_standings():
    try:
        rows, err = livescore_api.fetch_rpl_standings_rows()
        if err:
            return jsonify({"error": err, "standings": []}), 502
        table = []
        for r in rows:
            table.append({
                "position": r["position"],
                "team": {"name": r["team"], "crest": r.get("crest") or ""},
                "playedGames": r["played"],
                "won": r["won"],
                "draw": r["draw"],
                "lost": r["lost"],
                "goalsFor": r["goalsFor"],
                "goalsAgainst": r["goalsAgainst"],
                "points": r["points"],
            })
        return jsonify({
            "standings": [{
                "type": "TOTAL",
                "stage": "REGULAR_SEASON",
                "table": table,
            }],
        })
    except Exception as e:
        logger.exception("livescore_rpl_standings: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера", "standings": []}), 500


@app.route("/api/livescore/rpl/team-matches", methods=["GET"])
def livescore_rpl_team_matches():
    try:
        team = request.args.get("team", "").strip()
        if not team:
            return jsonify({"error": "Укажите параметр team.", "matches": []}), 400
        omit_hist = request.args.get("omit_history", "").strip().lower() in ("1", "true", "yes")
        matches, err = livescore_api.fetch_rpl_team_window(team, include_history=not omit_hist)
        if err:
            return jsonify({"error": err, "matches": matches or []}), 502
        return jsonify({"matches": matches})
    except Exception as e:
        logger.exception("livescore_rpl_team_matches: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера", "matches": []}), 500


@app.route("/api/livescore/rpl/match-stats", methods=["GET"])
def livescore_rpl_match_stats():
    try:
        raw_id = request.args.get("match_id")
        if not raw_id:
            return jsonify({"error": "Укажите match_id.", "data": []}), 400
        try:
            mid = int(float(str(raw_id).strip()))
        except (TypeError, ValueError):
            return jsonify({"error": "Некорректный match_id.", "data": []}), 400
        stats, err = livescore_api.fetch_match_stats(mid)
        if err:
            return jsonify({"error": err, "data": []}), 502
        return jsonify({"data": stats or []})
    except Exception as e:
        logger.exception("livescore_rpl_match_stats: %s", e)
        return jsonify({"error": "Внутренняя ошибка сервера", "data": []}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
