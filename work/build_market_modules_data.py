import json
import math
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path.home() / ".codex" / "config.toml"
OUTPUT_JSON = ROOT / "outputs" / "market_modules_data.json"
OUTPUT_JS = ROOT / "outputs" / "market_modules_data.js"
PERIOD_YEARS = ("1", "3", "5", "10", "20")


def get_token():
    text = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"https://api\.tushare\.pro/mcp/\?token=([^\"&\s]+)", text)
    if not match:
        raise RuntimeError("Tushare token was not found.")
    return match.group(1)


def call_api(token, api_name, params=None, fields=""):
    payload = json.dumps(
        {"api_name": api_name, "token": token, "params": params or {}, "fields": fields},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tushare.pro",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"{api_name}: {result.get('msg')}")
    data = result["data"]
    return [dict(zip(data["fields"], row)) for row in data["items"]]


def ymd(date_text):
    return datetime.strptime(date_text, "%Y%m%d")


def shift_years(date_text, years):
    date = ymd(date_text)
    try:
        shifted = date.replace(year=date.year - years)
    except ValueError:
        shifted = date.replace(year=date.year - years, day=28)
    return shifted.strftime("%Y%m%d")


def latest_daily_basic_date(token):
    today = datetime.now().strftime("%Y%m%d")
    rows = call_api(
        token,
        "trade_cal",
        {"exchange": "SSE", "start_date": shift_years(today, 1), "end_date": today, "is_open": "1"},
        "cal_date",
    )
    for date in sorted((row["cal_date"] for row in rows), reverse=True):
        probe = call_api(token, "daily_basic", {"trade_date": date}, "ts_code")
        if probe:
            return date
    raise RuntimeError("No recent daily_basic rows found.")


def finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def median(values):
    values = sorted(v for v in (finite(v) for v in values) if v is not None and v > 0)
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def pct(values, predicate):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(1 for v in values if predicate(v)) / len(values) * 100


def sample_dates(token, end_date, period_starts):
    rows = call_api(
        token,
        "trade_cal",
        {"exchange": "SSE", "start_date": period_starts["20"], "end_date": end_date, "is_open": "1"},
        "cal_date",
    )
    open_dates = sorted(row["cal_date"] for row in rows)
    month_last = {}
    for date in open_dates:
        month_last[date[:6]] = date
    monthly = sorted(month_last.values())

    def pick(start, max_points):
        dates = [d for d in monthly if d >= start]
        if len(dates) <= max_points:
            return dates
        last = len(dates) - 1
        return [dates[round(i * last / (max_points - 1))] for i in range(max_points)]

    by_period = {
        "1": pick(period_starts["1"], 13),
        "3": pick(period_starts["3"], 25),
        "5": pick(period_starts["5"], 31),
        "10": pick(period_starts["10"], 49),
        "20": pick(period_starts["20"], 72),
    }
    union = sorted({date for dates in by_period.values() for date in dates})
    if end_date not in union:
        union.append(end_date)
        union.sort()
    return by_period, union


def row_metrics(token, date):
    basic = call_api(
        token,
        "daily_basic",
        {"trade_date": date},
        "ts_code,trade_date,pe_ttm,pb,circ_mv,turnover_rate_f",
    )
    daily = call_api(token, "daily", {"trade_date": date}, "ts_code,trade_date,amount,pct_chg")
    margin_rows = []
    for exchange in ("SSE", "SZSE"):
        try:
            margin_rows += call_api(token, "margin", {"trade_date": date, "exchange_id": exchange}, "trade_date,exchange_id,rzye")
        except Exception:
            pass
    try:
        block_rows = call_api(token, "block_trade", {"trade_date": date}, "ts_code,trade_date,amount,vol")
    except Exception:
        block_rows = []

    pe_values = [row.get("pe_ttm") for row in basic]
    pb_values = [row.get("pb") for row in basic]
    turn_values = [row.get("turnover_rate_f") for row in basic]
    circ_mv = sum(finite(row.get("circ_mv")) or 0 for row in basic)
    amount = sum(finite(row.get("amount")) or 0 for row in daily)
    pct_chg = [finite(row.get("pct_chg")) for row in daily]
    margin_balance_yuan = sum(finite(row.get("rzye")) or 0 for row in margin_rows)
    block_amount = sum(finite(row.get("amount")) or 0 for row in block_rows)
    return {
        "date": date,
        "peMedian": round(median(pe_values), 2) if median(pe_values) else None,
        "pbMedian": round(median(pb_values), 2) if median(pb_values) else None,
        "highPeRatio": round(pct([finite(v) for v in pe_values], lambda v: v > 60), 2),
        "turnoverMedian": round(median(turn_values), 2) if median(turn_values) else None,
        "amountTotal": round(amount / 100000, 2),  # Tushare daily.amount is thousand yuan; output is 100m yuan.
        "limitUpCount": sum(1 for value in pct_chg if value is not None and value >= 9.8),
        "marginBalance": round(margin_balance_yuan / 100000000, 2) if margin_balance_yuan else None,
        "marginCircRatio": round(margin_balance_yuan / (circ_mv * 10000) * 100, 2) if margin_balance_yuan and circ_mv else None,
        "blockTradeAmount": round(block_amount / 10000, 2),  # Tushare block amount is 10k yuan; output is 100m yuan.
    }


def series(rows, key):
    return [row.get(key) for row in rows]


def percentile(rows, key):
    values = [row.get(key) for row in rows if row.get(key) is not None]
    latest = rows[-1].get(key) if rows else None
    if latest is None or not values:
        return None
    return round(sum(1 for value in values if value <= latest) / len(values) * 100)


def labels(rows):
    return [f'{row["date"][:4]}-{row["date"][4:6]}' for row in rows]


def trailing_ipo(token, dates, period_starts, end_date):
    all_rows = call_api(token, "new_share", {"start_date": period_starts["20"], "end_date": end_date}, "ts_code,name,ipo_date,amount,price")
    ipo_by_date = {}
    for row in all_rows:
        date = row.get("ipo_date")
        amount = finite(row.get("amount"))
        price = finite(row.get("price"))
        if not date or amount is None or price is None:
            continue
        ipo_by_date[date] = ipo_by_date.get(date, 0) + amount * price / 10000
    ordered = sorted(ipo_by_date.items())
    output = {}
    for date in dates:
        start = str(int(date[:4]) - 1) + date[4:]
        output[date] = round(sum(value for day, value in ordered if start <= day <= date), 2)
    return output


def hsgt_series(token, dates, period_starts, end_date):
    rows = call_api(token, "moneyflow_hsgt", {"start_date": period_starts["5"], "end_date": end_date}, "trade_date,north_money,south_money")
    by_date = {row["trade_date"]: finite(row.get("north_money")) for row in rows}
    available = sorted(by_date)
    output = {}
    for date in dates:
        prior = [d for d in available if d <= date]
        output[date] = by_date[prior[-1]] if prior else None
    return output


def main():
    token = get_token()
    end_date = latest_daily_basic_date(token)
    period_starts = {years: shift_years(end_date, int(years)) for years in PERIOD_YEARS}
    print(f"latest market date: {end_date}", flush=True)
    by_period, dates = sample_dates(token, end_date, period_starts)
    metrics_by_date = {}
    for idx, date in enumerate(dates, 1):
        print(f"[{idx}/{len(dates)}] {date}", flush=True)
        metrics_by_date[date] = row_metrics(token, date)
        time.sleep(0.05)

    ipo = trailing_ipo(token, dates, period_starts, end_date)
    north = hsgt_series(token, dates, period_starts, end_date)
    for date in dates:
        metrics_by_date[date]["ipoFinancing12m"] = ipo.get(date)
        metrics_by_date[date]["northMoney"] = north.get(date)

    periods = {}
    for years, period_dates in by_period.items():
        rows = [metrics_by_date[date] for date in period_dates if date in metrics_by_date]
        periods[years] = {
            "labels": labels(rows),
            "series": {
                "peMedian": series(rows, "peMedian"),
                "pbMedian": series(rows, "pbMedian"),
                "highPeRatio": series(rows, "highPeRatio"),
                "amountTotal": series(rows, "amountTotal"),
                "turnoverMedian": series(rows, "turnoverMedian"),
                "marginBalance": series(rows, "marginBalance"),
                "marginCircRatio": series(rows, "marginCircRatio"),
                "limitUpCount": series(rows, "limitUpCount"),
                "northMoney": series(rows, "northMoney"),
                "blockTradeAmount": series(rows, "blockTradeAmount"),
                "ipoFinancing12m": series(rows, "ipoFinancing12m"),
            },
            "percentiles": {
                key: percentile(rows, key)
                for key in (
                    "peMedian",
                    "pbMedian",
                    "highPeRatio",
                    "amountTotal",
                    "turnoverMedian",
                    "marginBalance",
                    "marginCircRatio",
                    "limitUpCount",
                    "northMoney",
                    "blockTradeAmount",
                    "ipoFinancing12m",
                )
            },
        }

    latest = metrics_by_date[end_date]
    payload = {
        "source": "Tushare daily_basic / daily / margin / moneyflow_hsgt / block_trade / new_share",
        "asOf": end_date,
        "periodStarts": period_starts,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "latest": latest,
        "periods": periods,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    OUTPUT_JS.write_text("window.MARKET_MODULES_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT_JSON), "dates": len(dates), "asOf": end_date}, ensure_ascii=False))


if __name__ == "__main__":
    main()
