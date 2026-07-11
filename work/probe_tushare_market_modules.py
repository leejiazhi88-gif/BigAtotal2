import json
import re
import urllib.request
from pathlib import Path


CONFIG = Path.home() / ".codex" / "config.toml"


def token():
    text = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"https://api\.tushare\.pro/mcp/\?token=([^\"&\s]+)", text)
    if not match:
        raise RuntimeError("Tushare token was not found.")
    return match.group(1)


def call(api_name, params=None, fields=""):
    payload = json.dumps(
        {"api_name": api_name, "token": token(), "params": params or {}, "fields": fields},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tushare.pro",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code") != 0:
        return {"ok": False, "msg": result.get("msg")}
    data = result.get("data", {})
    return {"ok": True, "fields": data.get("fields"), "rows": data.get("items", [])[:3], "count": len(data.get("items", []))}


def main():
    probes = {
        "daily_basic": ("daily_basic", {"trade_date": "20260618"}, "ts_code,trade_date,pe_ttm,pb,total_mv,circ_mv,turnover_rate_f"),
        "daily": ("daily", {"trade_date": "20260618"}, "ts_code,trade_date,amount,pct_chg,close"),
        "margin_sse": ("margin", {"trade_date": "20260618", "exchange_id": "SSE"}, "trade_date,exchange_id,rzye"),
        "margin_szse": ("margin", {"trade_date": "20260618", "exchange_id": "SZSE"}, "trade_date,exchange_id,rzye"),
        "moneyflow_hsgt": ("moneyflow_hsgt", {"start_date": "20260601", "end_date": "20260618"}, "trade_date,north_money,south_money"),
        "new_share": ("new_share", {"start_date": "20260101", "end_date": "20260618"}, "ts_code,name,ipo_date,amount,market_amount,price"),
        "block_trade": ("block_trade", {"trade_date": "20260618"}, "ts_code,trade_date,amount,vol"),
    }
    out = {name: call(*args) for name, args in probes.items()}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
