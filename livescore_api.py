"""
Proxy helpers for https://livescore-api.com/api-client/ (Russian Premier League).

Credentials: set LIVESCORE_API_KEY and LIVESCORE_API_SECRET in the environment
when running Flask. Do not commit real keys.
"""
from __future__ import annotations

import json
import os
import re
import ssl
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://livescore-api.com/api-client"
DEFAULT_RPL_COMPETITION_ID = "7"


def _competition_id() -> str:
    return os.environ.get("LIVESCORE_RPL_COMPETITION_ID", DEFAULT_RPL_COMPETITION_ID)


def _credentials() -> tuple[str | None, str | None]:
    return os.environ.get("LIVESCORE_API_KEY"), os.environ.get("LIVESCORE_API_SECRET")


def _safe_int(val: Any, default: int = 0) -> int:
    """API иногда отдаёт числа строкой, с запятой или как float-строку — int('1.0') падает."""
    if val is None:
        return default
    try:
        s = str(val).strip().replace(",", ".")
        if s == "":
            return default
        return int(float(s))
    except (TypeError, ValueError):
        return default


def _optional_team_id(val: Any) -> int | None:
    tid = _safe_int(val, 0)
    return tid if tid > 0 else None


def _as_list(val: Any) -> list:
    """LiveScore иногда отдаёт один объект вместо массива (match / fixtures / table)."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, dict):
        return [val]
    return []


def _ssl_context() -> ssl.SSLContext:
    """На macOS встроенный Python часто без CA — certifi решает SSL verify failed."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def livescore_get(path: str, params: dict[str, Any] | None = None) -> tuple[dict | None, str | None]:
    key, secret = _credentials()
    if not key or not secret:
        return None, "Задайте переменные окружения LIVESCORE_API_KEY и LIVESCORE_API_SECRET."

    q = {"key": key, "secret": secret}
    if params:
        for k, v in params.items():
            if v is None:
                continue
            q[k] = v
    url = f"{BASE}/{path.lstrip('/')}?{urlencode(q)}"
    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "footstat/1.0"})
        ctx = _ssl_context()
        with urlopen(req, timeout=25, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except HTTPError as e:
        return None, f"LiveScore HTTP {e.code}"
    except URLError as e:
        return None, f"LiveScore сеть: {e.reason}"
    except json.JSONDecodeError:
        return None, "LiveScore: невалидный JSON"
    except Exception as e:
        return None, f"LiveScore: {type(e).__name__}: {e}"

    if not data.get("success"):
        err = data.get("error") or data.get("message") or "Неизвестная ошибка LiveScore API"
        return None, str(err)
    return data, None


_SCORE_SPLIT = re.compile(r"\s*[-–]\s*")


def _parse_score(score_str: str | None) -> tuple[int | None, int | None]:
    if not score_str or not isinstance(score_str, str):
        return None, None
    parts = _SCORE_SPLIT.split(score_str.strip(), maxsplit=1)
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def _map_status(raw: str | None) -> str:
    s = (raw or "").upper().replace(" ", "_")
    if s in ("IN_PLAY", "ADDED_TIME"):
        return "IN_PLAY"
    if s in ("HALF_TIME_BREAK", "HT"):
        return "PAUSED"
    if s == "FINISHED":
        return "FINISHED"
    if s == "NOT_STARTED":
        return "TIMED"
    if s == "INSUFFICIENT_DATA":
        return "IN_PLAY"
    return "SCHEDULED"


def _iso_utc(date_str: str | None, time_str: str | None) -> str:
    d = (date_str or "").strip()
    t = (time_str or "12:00:00").strip()
    if len(t) == 5:
        t = f"{t}:00"
    if not d:
        return ""
    return f"{d}T{t}Z"


def _norm_team(side: dict | None) -> dict:
    if not side or not isinstance(side, dict):
        return {"name": "", "crest": ""}
    logo = side.get("logo") or ""
    return {"name": side.get("name") or "", "crest": logo}


def normalize_livescore_match(
    m: dict,
    *,
    fixture_id: int | None = None,
    utc_date: str | None = None,
) -> dict:
    home = _norm_team(m.get("home"))
    away = _norm_team(m.get("away"))
    scores = m.get("scores") or {}
    h, aw = _parse_score(scores.get("score") or scores.get("ft_score"))
    if h is None and m.get("outcomes"):
        pass

    date_s = m.get("date") or ""
    time_part = m.get("time") or m.get("scheduled") or "12:00"
    kick = utc_date or _iso_utc(str(date_s), str(time_part))

    mid = m.get("id")
    fid = fixture_id if fixture_id is not None else m.get("fixture_id")

    return {
        "id": mid or fid,
        "livescoreMatchId": mid,
        "fixtureId": fid,
        "utcDate": kick,
        "homeTeam": home,
        "awayTeam": away,
        "score": {"fullTime": {"home": h, "away": aw}},
        "status": _map_status(m.get("status")),
    }


def _fixture_calendar_day_and_time(f: dict, fallback_date: str | None) -> tuple[str, str]:
    """День матча YYYY-MM-DD и время; если API не прислал день — берём дату из запроса fixtures/list."""
    d = (
        str(f.get("date") or "").strip()
        or str(f.get("fixture_date") or "").strip()
        or str(f.get("match_date") or "").strip()
    )
    if not d and fallback_date:
        d = str(fallback_date).strip()
    t = str(f.get("time") or f.get("scheduled") or f.get("kick_off") or "12:00:00").strip()
    if len(t) == 5 and ":" in t and t.count(":") == 1:
        t = f"{t}:00"
    return d, t


def normalize_fixture(f: dict, fallback_date: str | None = None) -> dict:
    home = _norm_team(f.get("home"))
    away = _norm_team(f.get("away"))
    fid = f.get("id")
    day, tpart = _fixture_calendar_day_and_time(f, fallback_date)
    kick = _iso_utc(day, tpart)
    return {
        "id": f"fx-{fid}",
        "livescoreMatchId": None,
        "fixtureId": fid,
        "utcDate": kick,
        "homeTeam": home,
        "awayTeam": away,
        "score": {"fullTime": {"home": None, "away": None}},
        "status": "TIMED",
    }


def fetch_rpl_matches_for_date(iso_date: str) -> tuple[list[dict], str | None]:
    cid = _competition_id()
    today_iso = date.today().isoformat()
    merged: dict[tuple, dict] = {}

    def put(key: tuple, val: dict, priority: int):
        prev = merged.get(key)
        if not prev or priority >= prev["_p"]:
            val = dict(val)
            val["_p"] = priority
            merged[key] = val

    hist, err = livescore_get("matches/history.json", {"competition_id": cid, "from": iso_date, "to": iso_date, "lang": "ru"})
    if err:
        return [], err
    for m in _as_list(hist.get("data", {}).get("match")):
        if not isinstance(m, dict):
            continue
        nm = normalize_livescore_match(m)
        key = (nm["homeTeam"]["name"], nm["awayTeam"]["name"], iso_date)
        put(key, nm, 2)

    for page in range(1, 25):
        data, ferr = livescore_get(
            "fixtures/list.json",
            {"competition_id": cid, "date": iso_date, "lang": "ru", "page": page},
        )
        if ferr:
            return [], ferr
        block = data.get("data") or {}
        fixtures = _as_list(block.get("fixtures"))
        for f in fixtures:
            if not isinstance(f, dict):
                continue
            nm = normalize_fixture(f, iso_date)
            key = (nm["homeTeam"]["name"], nm["awayTeam"]["name"], iso_date)
            put(key, nm, 1)
        nxt = block.get("next_page")
        if not fixtures or not nxt or str(nxt).lower() in ("false", ""):
            break

    live, _ = livescore_get("matches/live.json", {"competition_id": cid, "lang": "ru"})
    if live:
        for m in _as_list(live.get("data", {}).get("match")):
            if not isinstance(m, dict):
                continue
            m_date = str(m.get("date") or "")
            if m_date and m_date != iso_date:
                continue
            if not m_date and iso_date != today_iso:
                continue
            nm = normalize_livescore_match(m)
            key = (nm["homeTeam"]["name"], nm["awayTeam"]["name"], iso_date)
            put(key, nm, 3)

    out = []
    for v in merged.values():
        v.pop("_p", None)
        out.append(v)
    out.sort(key=lambda x: x.get("utcDate") or "")
    return out, None


def fetch_rpl_live_matches() -> tuple[list[dict], str | None]:
    """Все live-матчи турнира (без фильтра по команде) — для вкладки Live."""
    cid = _competition_id()
    live, err = livescore_get("matches/live.json", {"competition_id": cid, "lang": "ru"})
    if err:
        return [], err
    out: list[dict] = []
    for m in _as_list(live.get("data", {}).get("match")):
        if isinstance(m, dict):
            out.append(normalize_livescore_match(m))
    return out, None


def _standings_rows_from_competition_table(data: dict) -> list[dict]:
    """Разбор competitions/table.json: у команд есть logo (CDN), имя — как в API (часто EN)."""
    rows: list[dict] = []
    for stage in _as_list((data.get("data") or {}).get("stages")):
        if not isinstance(stage, dict):
            continue
        for group in _as_list(stage.get("groups")):
            if not isinstance(group, dict):
                continue
            for entry in _as_list(group.get("standings")):
                if not isinstance(entry, dict):
                    continue
                team = entry.get("team") if isinstance(entry.get("team"), dict) else {}
                tid = _optional_team_id(team.get("id"))
                gf = _safe_int(entry.get("goals_scored"), 0)
                ga = _safe_int(entry.get("goals_conceded"), 0)
                rows.append({
                    "team_id": tid,
                    "name": str(team.get("name") or "-").strip(),
                    "logo": str(team.get("logo") or "").strip(),
                    "position": _safe_int(entry.get("rank"), 0),
                    "played": _safe_int(entry.get("matches"), 0),
                    "goalsFor": gf,
                    "goalsAgainst": ga,
                    "won": _safe_int(entry.get("won"), 0),
                    "draw": _safe_int(entry.get("drawn"), 0),
                    "lost": _safe_int(entry.get("lost"), 0),
                    "goalDiff": _safe_int(entry.get("goal_diff"), 0),
                    "points": _safe_int(entry.get("points"), 0),
                })
    rows.sort(key=lambda x: (x["position"], x["name"]))
    return rows


def fetch_rpl_standings_rows() -> tuple[list[dict], str | None]:
    cid = _competition_id()
    data, err = livescore_get("competitions/table.json", {"competition_id": cid, "lang": "ru"})
    if err or not data:
        return [], err
    parsed = _standings_rows_from_competition_table(data)
    if not parsed:
        return [], "Пустая таблица турнира."
    rows: list[dict] = []
    for r in parsed:
        rows.append({
            "position": r["position"],
            "team": r["name"],
            "crest": r["logo"],
            "played": r["played"],
            "goalsFor": r["goalsFor"],
            "goalsAgainst": r["goalsAgainst"],
            "won": r["won"],
            "draw": r["draw"],
            "lost": r["lost"],
            "goalDiff": r["goalDiff"],
            "points": r["points"],
        })
    return rows, None


_RPL_NAME_HINTS: tuple[tuple[str, str], ...] = (
    ("зенит", "zenit"),
    ("краснодар", "krasnodar"),
    ("цска", "cska"),
    ("спартак", "spartak"),
    ("локомотив", "lokomotiv"),
    ("ростов", "rostov"),
    ("рубин", "rubin"),
    ("ахмат", "akhmat"),
    ("нижний", "nizhny"),
    ("пари", "nizhny"),
    ("крылья", "krylya"),
    ("советов", "krylya"),
    ("сочи", "sochi"),
    ("урал", "ural"),
    ("оренбург", "orenburg"),
    ("балтика", "baltika"),
    ("факел", "fakel"),
    ("динамо махачкала", "makhachkala"),
    ("махачкала", "makhachkala"),
    ("акрон", "akron"),
    ("тольятти", "akron"),
    ("самара", "krylya"),
    ("казан", "rubin"),
    ("калининград", "baltika"),
)


def _team_match_rank(api_name: str, user_query: str) -> int:
    """Чем выше ранг — тем лучше совпадение (несколько московских клубов и т.п.)."""
    user = user_query.strip().lower()
    nl = api_name.strip().lower()
    if not user or not nl:
        return -1
    fav_mah = "махачкала" in user or "makhachkala" in user
    fav_dmo = ("динамо" in user or "dinamo" in user or "dynamo" in user) and (
        "москв" in user or "moscow" in user
    )
    api_mah = "makhachkala" in nl
    api_dmo = (
        ("dinamo" in nl or "dynamo" in nl) and "moscow" in nl and not api_mah
    ) or ("динамо" in nl and "москва" in nl and "махачкала" not in nl)
    if fav_mah:
        return 1000 if api_mah else -1
    if fav_dmo:
        return 1000 if api_dmo else -1
    if nl == user or user == nl:
        return 1000
    if user in nl or nl in user:
        return 500
    for ru_hint, en_hint in _RPL_NAME_HINTS:
        if ru_hint in user and en_hint in nl:
            return 100
    return -1


def team_id_and_name_from_table_api(team_name: str) -> tuple[int | None, str]:
    cid = _competition_id()
    data, err = livescore_get("competitions/table.json", {"competition_id": cid, "lang": "ru"})
    if err or not data:
        return None, team_name
    best: tuple[int, int, str] | None = None  # (rank, team_id, name)
    for r in _standings_rows_from_competition_table(data):
        name = r["name"]
        rank = _team_match_rank(name, team_name)
        if rank < 0:
            continue
        tid = r.get("team_id")
        if tid is None:
            continue
        cand = (rank, tid, name)
        if best is None or cand[0] > best[0]:
            best = cand
    if best is None:
        return None, team_name
    return best[1], best[2]


def fetch_rpl_team_window(team_name: str, *, include_history: bool = True) -> tuple[list[dict], str | None]:
    cid = _competition_id()
    tid, _canonical = team_id_and_name_from_table_api(team_name)
    if not tid:
        return [], f"Команда «{team_name}» не найдена в таблице РПЛ."

    merged: dict[str, dict] = {}

    def add(nm: dict):
        key = f"{nm.get('utcDate')}|{nm['homeTeam']['name']}|{nm['awayTeam']['name']}"
        merged[key] = nm

    live, _lerr = livescore_get("matches/live.json", {"competition_id": cid, "team_id": tid, "lang": "ru"})
    if not _lerr and live:
        for m in _as_list(live.get("data", {}).get("match")):
            if isinstance(m, dict):
                add(normalize_livescore_match(m))

    if include_history:
        hist, herr = livescore_get("matches/history.json", {"competition_id": cid, "team_id": tid, "lang": "ru"})
        if not herr and hist:
            for m in _as_list(hist.get("data", {}).get("match")):
                if isinstance(m, dict):
                    add(normalize_livescore_match(m))

    for page in range(1, 25):
        data, ferr = livescore_get(
            "fixtures/list.json",
            {"competition_id": cid, "team": tid, "lang": "ru", "page": page},
        )
        if ferr:
            break
        block = data.get("data") or {}
        fixtures = _as_list(block.get("fixtures"))
        for f in fixtures:
            if isinstance(f, dict):
                add(normalize_fixture(f))
        nxt = block.get("next_page")
        if not fixtures or not nxt or str(nxt).lower() in ("false", ""):
            break

    out = list(merged.values())
    out.sort(key=lambda x: x.get("utcDate") or "")
    return out, None


def fetch_match_stats(match_id: int) -> tuple[list[dict] | None, str | None]:
    data, err = livescore_get("statistics/matches.json", {"match_id": match_id, "lang": "ru"})
    if err:
        return None, err
    stats = data.get("data")
    if isinstance(stats, list):
        return stats, None
    return None, "Нет данных статистики"
