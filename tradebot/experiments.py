"""Run the experiments registered in RULES.md (IS + OOS backtests) and judge them by rules v2.

Usage:  python experiments.py [E1 E2 E3] [--telegram]
Writes user_data/results/experiments.md and experiments.json (the cockpit reads the json).
"""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from evaluate import RESULTS_DIR, compound, load_stats, send_telegram, summarize, verdict, fmt

ROOT = Path(__file__).parent
OUT_MD = ROOT / "user_data" / "results" / "experiments.md"
OUT_JSON = ROOT / "user_data" / "results" / "experiments.json"
RANGES = {"IS": "20250926-20260626", "OOS": "20260626-20260926"}
BASE = ["--config", "user_data/config.json", "--config", "user_data/config.bitvavo.json",
        # Stake as registered for E1-E3 (RULES.md v3): the base config now uses a fixed 20 EUR.
        "--config", "user_data/config.registered.json"]

EXPERIMENTS = {
    "E1": {"strategy": "DrakenGamma", "service": "freqtrade", "args": []},
    "E2": {"strategy": "MomentumRotation", "service": "freqtrade",
           "args": ["--config", "user_data/config.rotation.json"]},
    "E3": {"strategy": "FreqAIRegime", "service": "freqai-tools",
           "args": ["--config", "user_data/config.freqai.json", "--freqaimodel", "LightGBMRegressor"]},
}


def run(exp_id: str, rng: str) -> None:
    e = EXPERIMENTS[exp_id]
    name = f"bitvavo_{rng}_{e['strategy']}_1h"
    out = RESULTS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    cmd = ["docker", "compose", "run", "--rm", e["service"], "backtesting", *BASE, *e["args"],
           "--strategy", e["strategy"], "--timeframe", "1h", "--timerange", RANGES[rng],
           "--export", "trades", "--cache", "none", "--enable-protections",
           "--backtest-directory", f"user_data/backtest_results/{name}"]
    print(f"=== {exp_id} {rng} {e['strategy']}", flush=True)
    log = ROOT / "user_data" / "results" / f"{name}.txt"
    with open(log, "w", encoding="utf-8") as fh:
        res = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
    if res.returncode:
        print(f"    FAILED (exit {res.returncode}), see {log}", flush=True)


def judge(exp_id: str) -> dict:
    s = EXPERIMENTS[exp_id]["strategy"]
    is_ = summarize(load_stats(RESULTS_DIR / f"bitvavo_IS_{s}_1h", s))
    oos = summarize(load_stats(RESULTS_DIR / f"bitvavo_OOS_{s}_1h", s))
    v1, v2, reasons = verdict(is_, oos)
    return {"id": exp_id, "exchange": "bitvavo", "strategy": s, "timeframe": "1h",
            "is": is_, "oos": oos,
            "full": compound(is_["profit"], oos["profit"]) if is_ and oos else None,
            "full_hold": compound(is_["hold"], oos["hold"]) if is_ and oos else None,
            "pass_v1": v1, "pass_v2": v2, "reasons": reasons}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", default=list(EXPERIMENTS))
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--judge-only", action="store_true")
    args = ap.parse_args()

    if not args.judge_only:
        for exp_id in args.ids:
            for rng in RANGES:
                run(exp_id, rng)

    records = [judge(i) for i in EXPERIMENTS]
    lines = ["# Experiment report (RULES.md, registered 2026-09-26)", "",
             "| Exp | Strategy | In-sample | Out-of-sample | Full period vs hold | Verdict |",
             "|---|---|---|---|---|---|"]
    for r in records:
        full = "-" if r["full"] is None else f"{r['full']:+.1%} vs {r['full_hold']:+.1%}"
        verdict_txt = "PASS" if r["pass_v2"] else "; ".join(r["reasons"])
        lines.append(f"| {r['id']} | {r['strategy']} | {fmt(r['is'])} | {fmt(r['oos'])} | {full} | {verdict_txt} |")
    passed = [r for r in records if r["pass_v2"]]
    summary = (f"Experiments: {len(passed)}/{len(records)} pass rules v2"
               + (": " + ", ".join(f"{r['id']} {r['strategy']}" for r in passed) if passed else "."))
    lines += ["", summary]

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps({"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "summary": summary, "results": records}, indent=1), encoding="utf-8")
    print("\n".join(lines))
    if args.telegram:
        p = lambda v: "-" if v is None else f"{v:+.1%}"  # noqa: E731
        body = "\n".join(
            f"{r['id']} {r['strategy']}: full year {p(r['full'])} vs hold {p(r['full_hold'])} → "
            f"{'PASS' if r['pass_v2'] else 'fail'}" for r in records)
        send_telegram("🧪 " + summary + "\n" + body)


if __name__ == "__main__":
    main()
