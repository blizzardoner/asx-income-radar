#!/usr/bin/env python3
import json
from pathlib import Path

from update_market_data import OUTPUT_PATH, UNIVERSE_PATH, update_market_data

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "alert-state.json"


def evaluate_status(stock, market):
    if market.get("dataAgeDays", 99) > 7:
        return "STALE", 0.0, 0.0
    sustainable_dps = stock.get("sustainableDpsOverride")
    if sustainable_dps is None:
        sustainable_dps = market["trailingCashDps"] * stock["stabilityFactor"]
    buy_price = sustainable_dps / stock["requiredCashYield"]
    cash_yield = sustainable_dps / market["price"]
    if (
        market["price"] <= buy_price
        and stock["quality"] != "C"
        and stock["payoutCoverage"] >= 1
    ):
        return "BUY", buy_price, cash_yield
    if market["price"] <= buy_price * 1.08:
        return "WATCH", buy_price, cash_yield
    return "WAIT", buy_price, cash_yield


def build_alerts(universe, market_data, previous):
    alerts = []
    statuses = {}
    labels = {"BUY": "进入买入区", "WATCH": "接近买点"}
    for stock in universe:
        market = market_data.get("stocks", {}).get(stock["ticker"])
        if not market:
            continue
        status, buy_price, cash_yield = evaluate_status(stock, market)
        statuses[stock["ticker"]] = status
        if status in labels and previous.get(stock["ticker"]) != status:
            code = stock["ticker"].replace(".AX", "")
            alerts.append(
                f"ASX高息股提醒｜{code} {stock['name']} 已{labels[status]}："
                f"现价A${market['price']:.2f}，硬买入价A${buy_price:.2f}，"
                f"模型可持续现金收益率{cash_yield * 100:.1f}%。"
            )
    return alerts, statuses


def main():
    update_market_data()
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    market_data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    first_run = not STATE_PATH.exists()
    previous = json.loads(STATE_PATH.read_text(encoding="utf-8")) if not first_run else {}
    alerts, statuses = build_alerts(universe, market_data, previous)
    STATE_PATH.write_text(json.dumps(statuses, indent=2), encoding="utf-8")
    if not first_run and alerts:
        print("\n".join(alerts))


if __name__ == "__main__":
    main()
