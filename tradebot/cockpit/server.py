"""Draken cockpit: local dashboard + Telegram reporter for the paper-trading bots.

- Serves cockpit.html and a JSON overview built from each bot's Freqtrade REST API.
- Relays pause / resume / stop to the bots (POST only from the cockpit page itself).
- Receives Freqtrade webhooks (entry/exit fills, status, warnings) and forwards them to Telegram.
- Sends a summary to Telegram at SUMMARY_HOURS, and alerts when a bot stops answering.

Standard library only. Runs in python:3.12-slim; see docker-compose.yml.
"""
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).parent
ASSETS = (APP / "assets").resolve()
ASSET_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".webp": "image/webp"}
STATE = Path(os.environ.get("STATE_DIR", "/state"))
RESULTS = Path(os.environ.get("RESULTS_DIR", "/results")) / "results.json"
BOTS = dict(item.split("=", 1) for item in os.environ["BOTS"].split(","))
AUTH = "Basic " + base64.b64encode(
    f"{os.environ.get('FREQTRADE__API_SERVER__USERNAME', 'draken')}:"
    f"{os.environ['FREQTRADE__API_SERVER__PASSWORD']}".encode()).decode()
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
HOOK_TOKEN = os.environ.get("HOOK_TOKEN", "")
SUMMARY_HOURS = {int(h) for h in os.environ.get("SUMMARY_HOURS", "8,20").split(",")}
PAIRS = ["BTC/EUR", "ETH/EUR", "SOL/EUR"]
CONTROL_ACTIONS = {"stopentry", "start", "stop"}
ALLOWED_ORIGINS = {"http://127.0.0.1:8090", "http://localhost:8090"}

STATE.mkdir(parents=True, exist_ok=True)
EVENTS_FILE = STATE / "events.json"
_lock = threading.Lock()


# ---------- helpers ----------

def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def bot_api(bot: str, endpoint: str, method: str = "GET", timeout: float = 8):
    req = urllib.request.Request(f"{BOTS[bot]}/api/v1/{endpoint}", method=method,
                                 headers={"Authorization": AUTH})
    if method == "POST":
        req.data = b"{}"
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def telegram(text: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        log("telegram not configured:", text)
        return
    body = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                               data=body, timeout=15).read()
    except Exception as e:  # never let Telegram trouble break the cockpit
        log("telegram send failed:", e)


def load_events() -> list:
    try:
        return json.loads(EVENTS_FILE.read_text())
    except Exception:
        return []


def add_event(ev: dict) -> None:
    with _lock:
        events = load_events()
        events.append(ev)
        EVENTS_FILE.write_text(json.dumps(events[-300:]))


def num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def eur(v: float) -> str:
    return ("+" if v >= 0 else "−") + f"€{abs(v):.2f}"


def pct(v: float) -> str:
    return ("+" if v >= 0 else "−") + f"{abs(v) * 100:.2f}%"


# ---------- overview (shared by the page and the Telegram summary) ----------

def bot_overview(bot: str) -> dict:
    try:
        cfg = bot_api(bot, "show_config")
        bal = bot_api(bot, "balance")
        health = bot_api(bot, "health")
        trades = bot_api(bot, "trades?limit=500").get("trades", [])
        open_trades = bot_api(bot, "status")
    except Exception as e:
        return {"bot": bot, "online": False, "error": str(e)}

    start_cap = num(bal.get("starting_capital")) or num(cfg.get("dry_run_wallet"), 90.0)
    closed = sorted((t for t in trades if not t.get("is_open")),
                    key=lambda t: t.get("close_timestamp") or 0)
    equity, cum, fees_total = [], 0.0, 0.0
    for t in closed:
        fees = num(t.get("fee_open_cost")) + num(t.get("fee_close_cost"))
        fees_total += fees
        cum += num(t.get("profit_abs"))
        equity.append([t["close_timestamp"], cum / start_cap])
    open_fees = sum(num(t.get("fee_open_cost")) for t in open_trades)
    wins = sum(1 for t in closed if num(t.get("profit_abs")) > 0)
    total = num(bal.get("total"), start_cap)
    return {
        "bot": bot, "online": True,
        "name": cfg.get("bot_name"), "strategy": cfg.get("strategy"),
        "timeframe": cfg.get("timeframe"), "state": cfg.get("state"),
        "dry_run": cfg.get("dry_run"), "exchange": cfg.get("exchange"),
        "started": health.get("bot_startup_ts") or health.get("bot_start_ts"),
        "last_process": health.get("last_process_ts"),
        "starting_capital": start_cap, "balance": total,
        # Freqtrade's balance leaves out coins held in open trades, so value the wallet as
        # starting capital + closed profit + open trades' unrealised profit
        "return": (cum + sum(num(t.get("profit_abs")) for t in open_trades)) / start_cap
                  if start_cap else 0.0,
        "closed_profit": cum, "fees": fees_total + open_fees,
        "wins": wins, "losses": len(closed) - wins,
        "equity": equity,
        "open_trades": [{k: t.get(k) for k in (
            "trade_id", "pair", "open_rate", "current_rate", "stake_amount",
            "profit_ratio", "profit_abs", "open_timestamp")} for t in open_trades],
        "closed_trades": [{k: t.get(k) for k in (
            "trade_id", "pair", "open_rate", "close_rate", "stake_amount", "profit_ratio",
            "profit_abs", "exit_reason", "open_timestamp", "close_timestamp",
            "fee_open_cost", "fee_close_cost")} for t in closed[-100:]],
    }


def hold_series(since_ms: int) -> list:
    """Equal-weight buy-and-hold of PAIRS since since_ms, as [[ts_ms, return], ...]."""
    for bot in BOTS:
        try:
            closes = {}
            for pair in PAIRS:
                q = urllib.parse.urlencode({"pair": pair, "timeframe": "1h", "limit": 1000})
                d = bot_api(bot, f"pair_candles?{q}", timeout=15)
                cols = d["columns"]
                i_t, i_c = cols.index("__date_ts"), cols.index("close")
                # Include two candles before the start so the baseline is the last close before it
                closes[pair] = {row[i_t]: row[i_c] for row in d["data"] if row[i_t] >= since_ms - 2 * 3600_000}
            common = sorted(set.intersection(*(set(c) for c in closes.values())))
            if not common:
                return []
            base = {p: closes[p][common[0]] for p in PAIRS}
            return [[ts, sum(closes[p][ts] / base[p] for p in PAIRS) / len(PAIRS) - 1] for ts in common]
        except Exception as e:
            log("hold series from", bot, "failed:", e)
    return []


def overview() -> dict:
    bots = [bot_overview(b) for b in BOTS]
    starts = [b["started"] for b in bots if b.get("online") and b.get("started")]
    since = int(min(starts) * 1000) if starts else int(time.time() * 1000) - 86400_000
    return {"generated": int(time.time() * 1000), "bots": bots,
            "hold": hold_series(since), "pairs": PAIRS}


GAMMA_COLS = ["close", "gamma", "consensus", "view_mean_0", "view_mean_1", "view_mean_2",
              "s_dist", "s_slope", "s_mom", "s_dist_4h", "s_slope_4h", "s_mom_4h",
              "s_dist_1d", "s_slope_1d", "s_mom_1d", "enter_long", "exit_long"]


def gamma_state() -> dict:
    """Latest coherence readings from the DrakenGamma bot, plus 7 days of history per pair."""
    if "gamma" not in BOTS:
        return {"pairs": []}
    out = []
    for pair in PAIRS:
        q = urllib.parse.urlencode({"pair": pair, "timeframe": "1h", "limit": 170})
        try:
            d = bot_api("gamma", f"pair_candles?{q}", timeout=15)
        except Exception as e:
            out.append({"pair": pair, "error": str(e)})
            continue
        cols = d.get("columns", [])
        if "gamma" not in cols:
            out.append({"pair": pair, "error": "no analysed candles yet"})
            continue
        idx = {c: cols.index(c) for c in GAMMA_COLS + ["__date_ts"] if c in cols}
        rows = [{c: r[i] for c, i in idx.items()} for r in d["data"]]
        out.append({"pair": pair, "latest": rows[-1] if rows else None,
                    "series": [[r["__date_ts"], r.get("gamma"), r.get("consensus")] for r in rows]})
    return {"pairs": out, "enter": 0.80, "exit": 0.55, "consensus_enter": 0.25}


def gamma_word(row: dict) -> str:
    g, c = row.get("gamma"), row.get("consensus")
    if g is None or c is None:
        return "warming up"
    if g >= 0.80 and c > 0.25:
        return "coherent ↑"
    if g >= 0.80 and c < -0.25:
        return "coherent ↓"
    if g < 0.55:
        return "split"
    return "partly aligned"


# ---------- Telegram texts ----------

def hook_text(bot: str, ev: dict) -> str | None:
    kind = ev.get("event")
    tag = f"[{bot}] paper"
    if kind == "entry":
        return (f"🟢 {tag} BUY {ev.get('pair')} @ {num(ev.get('rate')):,.4g}\n"
                f"Stake €{num(ev.get('stake')):.2f}")
    if kind == "exit":
        p, r = num(ev.get("profit_abs")), num(ev.get("profit_ratio"))
        icon = "✅" if p > 0 else "🔴"
        return (f"{icon} {tag} SELL {ev.get('pair')} {pct(r)} ({eur(p)})\n"
                f"{num(ev.get('open_rate')):,.4g} → {num(ev.get('rate')):,.4g} · reason: {ev.get('reason')}")
    if kind in ("status", "warning"):  # startup chatter is not subscribed in config.json
        return f"{'⚠️' if kind == 'warning' else 'ℹ️'} [{bot}] {ev.get('status', '')}"
    return None


def summary_text(ov: dict) -> str:
    lines = [f"📊 Draken paper summary · {datetime.now():%a %d %b %H:%M}"]
    hold = ov["hold"][-1][1] if ov["hold"] else None
    for b in ov["bots"]:
        if not b.get("online"):
            lines.append(f"\n{b['bot']}: OFFLINE ({b.get('error', '')[:80]})")
            continue
        n = b["wins"] + b["losses"]
        lines.append(
            f"\n{b['bot']} · {b['strategy']} {b['timeframe']} · {b['state']}\n"
            f"Balance €{b['balance']:.2f} ({pct(b['return'])})\n"
            f"Closed {n}: {b['wins']} wins / {b['losses']} losses · open {len(b['open_trades'])}\n"
            f"Fees paid €{b['fees']:.2f}")
    if hold is not None:
        lines.append(f"\nHolding BTC/ETH/SOL since start: {pct(hold)}")
    try:
        g = [x for x in gamma_state()["pairs"] if (x.get("latest") or {}).get("gamma") is not None]
        if g:
            lines.append("\nΓ now: " + " · ".join(
                f"{x['pair'].split('/')[0]} {x['latest']['gamma']:.2f} {gamma_word(x['latest'])}"
                for x in g))
    except Exception as e:
        log("gamma summary failed:", e)
    return "\n".join(lines)


# ---------- background loop: summaries + bot-down alerts ----------

def scheduler():
    last_key, down_since, alerted = None, {}, set()
    telegram("🐉 Draken cockpit started. Paper trading only. Summaries at "
             + ", ".join(f"{h:02d}:00" for h in sorted(SUMMARY_HOURS)) + ".")
    while True:
        now = datetime.now()
        key = now.strftime("%Y-%m-%d %H")
        if now.hour in SUMMARY_HOURS and key != last_key:
            last_key = key
            try:
                telegram(summary_text(overview()))
            except Exception as e:
                log("summary failed:", e)
        for bot in BOTS:
            try:
                bot_api(bot, "ping", timeout=5)
                if bot in alerted:
                    telegram(f"✅ [{bot}] is answering again.")
                    alerted.discard(bot)
                down_since.pop(bot, None)
            except Exception:
                first = down_since.setdefault(bot, time.time())
                if time.time() - first > 600 and bot not in alerted:
                    telegram(f"⚠️ [{bot}] has not answered for 10 minutes.")
                    alerted.add(bot)
        time.sleep(30)


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, code: int, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self.send(200, (APP / "cockpit.html").read_bytes(), "text/html; charset=utf-8")
        if path.startswith("/assets/"):
            # Static images for the page: a bare file name in cockpit/assets, known types only
            name = path[len("/assets/"):]
            ctype = ASSET_TYPES.get(Path(name).suffix.lower())
            f = (ASSETS / name).resolve()
            if ctype and "/" not in name and "\\" not in name and f.parent == ASSETS and f.is_file():
                return self.send(200, f.read_bytes(), ctype)
            return self.send(404, {"error": "not found"})
        if path == "/api/overview":
            return self.send(200, overview())
        if path == "/api/results":
            merged = {"results": []}
            for f in (RESULTS, RESULTS.with_name("experiments.json")):
                try:
                    merged["results"] += json.loads(f.read_text(encoding="utf-8"))["results"]
                except (FileNotFoundError, KeyError, json.JSONDecodeError):
                    pass
            return self.send(200, merged)
        if path == "/api/gamma":
            return self.send(200, gamma_state())
        if path == "/api/events":
            return self.send(200, load_events()[-60:])
        return self.send(404, {"error": "not found"})

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        parts = url.path.strip("/").split("/")
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""

        # Webhooks from the bots (inside the Docker network), authenticated by token.
        if len(parts) == 2 and parts[0] == "hook" and parts[1] in BOTS:
            token = urllib.parse.parse_qs(url.query).get("t", [""])[0]
            if not HOOK_TOKEN or token != HOOK_TOKEN:
                return self.send(403, {"error": "bad token"})
            try:
                ev = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return self.send(400, {"error": "bad json"})
            ev["bot"], ev["ts"] = parts[1], int(time.time() * 1000)
            add_event(ev)
            text = hook_text(parts[1], ev)
            if text:
                threading.Thread(target=telegram, args=(text,), daemon=True).start()
            return self.send(200, {"ok": True})

        # Everything else must come from the cockpit page itself (blocks cross-site requests).
        if self.headers.get("Origin") not in ALLOWED_ORIGINS:
            return self.send(403, {"error": "forbidden origin"})
        if parts == ["api", "summary"]:
            telegram(summary_text(overview()))
            return self.send(200, {"ok": True})
        if len(parts) == 3 and parts[0] == "api" and parts[1] in BOTS and parts[2] in CONTROL_ACTIONS:
            try:
                res = bot_api(parts[1], parts[2], method="POST")
            except urllib.error.URLError as e:
                return self.send(502, {"error": str(e)})
            add_event({"bot": parts[1], "event": "control", "status": parts[2],
                       "ts": int(time.time() * 1000)})
            telegram(f"🎛 [{parts[1]}] {parts[2]} (from cockpit)")
            return self.send(200, res)
        return self.send(404, {"error": "not found"})


if __name__ == "__main__":
    threading.Thread(target=scheduler, daemon=True).start()
    log("cockpit on :8090, bots:", ", ".join(BOTS))
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
