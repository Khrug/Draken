"""Apply the decision rules in RULES.md to the backtest matrix and write a pass/fail report.

v1 rules (OOS window): profit after fees > 0, >= 30 trades, max drawdown <= 15 %.
v2 adds: in-sample return beats buy-and-hold, and full-period return beats buy-and-hold.
Rules are fixed in RULES.md - do not edit them here after looking at results.

Reads user_data/backtest_results/<exchange>_<IS|OOS>_<strategy>_<tf>/ (written by
run_backtests.ps1), writes user_data/results/report.md and results.json (read by the
cockpit), and optionally sends a summary to Telegram.
Standard library only, so it runs on the host without installing anything.
"""
import argparse
import json
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
RESULTS_DIR = ROOT / "user_data" / "backtest_results"
REPORT = ROOT / "user_data" / "results" / "report.md"
RESULTS_JSON = ROOT / "user_data" / "results" / "results.json"

MIN_TRADES = 30
MAX_DRAWDOWN = 0.15

STRATEGIES = ["TrendEmaAdx", "MeanRevBbRsi", "BreakoutDonchian"]
# Venue -> (taker fee per side, timeframes). Must match run_backtests.ps1.
# Revolut X public candles only reach back far enough for 1h (15m/30m: about one month).
VENUES = {
    "revolutx": ("0.09 %", ["1h"]),
    "revolutx-stress": ("0.19 % (stress: +0.10 %)", ["1h"]),
}
EXCHANGES = {k: v[0] for k, v in VENUES.items()}


def load_stats(run_dir: Path, strategy: str) -> dict | None:
    """Return the strategy stats dict from the newest backtest result in run_dir."""
    zips = sorted(run_dir.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        return None
    with zipfile.ZipFile(zips[-1]) as zf:
        # The main result is the .json that isn't a config/strategy/market-change sidecar
        main = [n for n in zf.namelist() if n.endswith(".json")
                and not n.endswith(("_config.json", "_market_change.json"))
                and "_" + strategy + ".json" not in n]
        for name in main:
            data = json.loads(zf.read(name))
            if "strategy" in data and strategy in data["strategy"]:
                return data["strategy"][strategy]
    return None


def summarize(stats: dict | None) -> dict | None:
    if stats is None:
        return None
    return {
        "trades": int(stats.get("total_trades", 0)),
        "profit": float(stats.get("profit_total", 0.0)),
        "drawdown": float(stats.get("max_drawdown_account", 0.0)),
        "winrate": float(stats.get("winrate", 0.0)),
        "profit_factor": float(stats.get("profit_factor", 0.0) or 0.0),
        "hold": float(stats.get("market_change", 0.0)),
    }


def compound(a: float, b: float) -> float:
    return (1 + a) * (1 + b) - 1


def verdict(is_: dict | None, oos: dict | None) -> tuple[bool, bool, list[str]]:
    """Return (passes v1, passes v2, reasons)."""
    if is_ is None or oos is None:
        return False, False, ["no result"]
    v1 = []
    if oos["profit"] <= 0:
        v1.append("OOS profit <= 0")
    if oos["trades"] < MIN_TRADES:
        v1.append(f"trades < {MIN_TRADES}")
    if oos["drawdown"] > MAX_DRAWDOWN:
        v1.append(f"drawdown > {MAX_DRAWDOWN:.0%}")
    v2 = []
    if is_["profit"] <= is_["hold"]:
        v2.append("IS below hold")
    if compound(is_["profit"], oos["profit"]) <= compound(is_["hold"], oos["hold"]):
        v2.append("full period below hold")
    return not v1, not v1 and not v2, v1 + v2


def fmt(s: dict | None) -> str:
    if s is None:
        return "-"
    return f"{s['profit']:+.2%} / {s['trades']} tr / DD {s['drawdown']:.1%}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--telegram", action="store_true", help="send summary to Telegram (.env)")
    args = ap.parse_args()

    rows, records = [], []
    for ex, (_, timeframes) in VENUES.items():
        for strat in STRATEGIES:
            for tf in timeframes:
                is_ = summarize(load_stats(RESULTS_DIR / f"{ex}_IS_{strat}_{tf}", strat))
                oos = summarize(load_stats(RESULTS_DIR / f"{ex}_OOS_{strat}_{tf}", strat))
                v1, v2, reasons = verdict(is_, oos)
                full = compound(is_["profit"], oos["profit"]) if is_ and oos else None
                full_hold = compound(is_["hold"], oos["hold"]) if is_ and oos else None
                label = "PASS" if v2 else ("v1 only: " if v1 else "") + "; ".join(reasons)
                rows.append(f"| {ex} | {strat} | {tf} | {fmt(is_)} | {fmt(oos)} | "
                            f"{'-' if full is None else f'{full:+.1%} vs {full_hold:+.1%}'} | {label} |")
                records.append({"exchange": ex, "strategy": strat, "timeframe": tf,
                                "is": is_, "oos": oos, "full": full, "full_hold": full_hold,
                                "pass_v1": v1, "pass_v2": v2, "reasons": reasons})

    v1_n = sum(r["pass_v1"] for r in records)
    survivors = sorted((r for r in records if r["pass_v2"]), key=lambda r: r["full"], reverse=True)
    lines = [
        "# Backtest report",
        "",
        f"Rules (RULES.md v2): OOS profit > 0, >= {MIN_TRADES} OOS trades, OOS drawdown <= "
        f"{MAX_DRAWDOWN:.0%}, in-sample beats hold, full period beats hold. "
        "Taker fee per side: " + ", ".join(f"{k} {v}" for k, v in EXCHANGES.items()) + ".",
        "",
        "| Exchange | Strategy | TF | In-sample (profit / trades / DD) | Out-of-sample | Full period vs hold | Verdict |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
    ]
    if survivors:
        b = survivors[0]
        lines.append(f"**Survivors:** {len(survivors)}/{len(rows)} under v2 ({v1_n} under v1). "
                     f"Best full period: {b['exchange']} {b['strategy']} {b['timeframe']} "
                     f"({b['full']:+.1%} vs hold {b['full_hold']:+.1%}).")
    else:
        lines.append(f"**Survivors:** 0/{len(rows)} under v2 ({v1_n} under v1). "
                     "That is a valid result - do not tune until something passes.")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    RESULTS_JSON.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rules": "v2", "fees": EXCHANGES, "summary": lines[-1].replace("**", ""),
        "results": records}, indent=1), encoding="utf-8")
    print("\n".join(lines))

    if args.telegram:
        send_telegram("Backtest report: " + lines[-1].replace("**", ""))


def load_env() -> dict:
    env = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def send_telegram(text: str) -> None:
    env = load_env()
    token, chat = env.get("TELEGRAM_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("Telegram not configured in .env; skipping.")
        return
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=body, timeout=15)


if __name__ == "__main__":
    main()
