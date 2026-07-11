import json
import math
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path.home() / ".codex" / "config.toml"
OUTPUT = ROOT / "outputs" / "sector_real_data.json"
START_DATE = "20060101"
END_DATE = "20260618"
PERIODS = {
    "1": "20250618",
    "3": "20230619",
    "5": "20210618",
    "20": "20060619",
}


def get_token():
    text = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"https://api\.tushare\.pro/mcp/\?token=([^\"&\s]+)", text)
    if not match:
        raise RuntimeError("Tushare token was not found in the local Codex config.")
    return match.group(1)


def call_api(token, api_name, params, fields):
    payload = json.dumps(
        {"api_name": api_name, "token": token, "params": params, "fields": fields},
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


def clean_name(name):
    return re.sub(r"[ⅠⅡⅢ]+$", "", name or "")


def ymd(date_text):
    return datetime.strptime(date_text, "%Y%m%d")


def sample_rows(rows, start_date, max_points):
    filtered = [row for row in rows if row["trade_date"] >= start_date and row.get("close")]
    if len(filtered) < 2:
        return []
    filtered.sort(key=lambda row: row["trade_date"])
    span_days = (ymd(filtered[-1]["trade_date"]) - ymd(start_date)).days
    # If the index did not exist near the requested start, do not pretend this is a full-period series.
    first_gap = (ymd(filtered[0]["trade_date"]) - ymd(start_date)).days
    if span_days > 365 and first_gap > 90:
        return []
    if len(filtered) <= max_points:
        return filtered
    picked = []
    last_index = len(filtered) - 1
    for i in range(max_points):
        idx = round(i * last_index / (max_points - 1))
        if not picked or picked[-1]["trade_date"] != filtered[idx]["trade_date"]:
            picked.append(filtered[idx])
    return picked


def normalize_series(rows, key):
    vals = []
    for row in rows:
        value = row.get(key)
        if value is None:
            vals.append(None)
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            vals.append(None)
            continue
        vals.append(value if math.isfinite(value) else None)
    if key == "close" and vals and vals[0]:
        base = vals[0]
        return [None if value is None else round(value / base * 100, 2) for value in vals]
    if key == "profit":
        valid = next((value for value in vals if value and value > 0), None)
        if valid:
            return [None if value is None else round(value / valid * 100, 2) for value in vals]
    return [None if value is None else round(value, 2) for value in vals]


def implied_profit(row):
    pe = row.get("pe")
    mv = row.get("total_mv")
    if pe is None or mv is None:
        return None
    try:
        pe = float(pe)
        mv = float(mv)
    except (TypeError, ValueError):
        return None
    if pe <= 0 or not math.isfinite(pe) or not math.isfinite(mv):
        return None
    return mv / pe


def build_history(rows):
    rows = [row for row in rows if row.get("trade_date")]
    rows.sort(key=lambda row: row["trade_date"])
    for row in rows:
        row["profit"] = implied_profit(row)
    latest = rows[-1] if rows else {}
    periods = {}
    max_points = {"1": 64, "3": 72, "5": 72, "20": 96}
    for years, start in PERIODS.items():
        sample = sample_rows(rows, start, max_points[years])
        if not sample:
            periods[years] = None
            continue
        close_values = [float(row["close"]) for row in sample]
        ret = (close_values[-1] / close_values[0] - 1) * 100
        pe_values = [row.get("pe") for row in sample if row.get("pe") is not None]
        latest_pe = latest.get("pe")
        pe_percentile = None
        if latest_pe is not None and pe_values:
            ordered = sorted(float(v) for v in pe_values if float(v) > 0)
            if ordered:
                rank = sum(1 for value in ordered if value <= float(latest_pe))
                pe_percentile = round(rank / len(ordered) * 100)
        periods[years] = {
            "labels": [f'{row["trade_date"][:4]}-{row["trade_date"][4:6]}' for row in sample],
            "price": normalize_series(sample, "close"),
            "profit": normalize_series(sample, "profit"),
            "pe": normalize_series(sample, "pe"),
            "return": round(ret, 2),
            "startDate": sample[0]["trade_date"],
            "endDate": sample[-1]["trade_date"],
            "pePercentile": pe_percentile,
        }
    return {
        "latest": {
            "date": latest.get("trade_date"),
            "close": round(float(latest["close"]), 2) if latest.get("close") is not None else None,
            "pe": round(float(latest["pe"]), 2) if latest.get("pe") is not None else None,
            "totalMv": round(float(latest["total_mv"]), 2) if latest.get("total_mv") is not None else None,
            "profit": round(implied_profit(latest), 2) if implied_profit(latest) else None,
        },
        "periods": periods,
    }


def main():
    token = get_token()
    l1_rows = call_api(token, "index_classify", {"src": "SW2021", "level": "L1"}, "index_code,industry_name,parent_code,level,industry_code")
    l2_rows = call_api(token, "index_classify", {"src": "SW2021", "level": "L2"}, "index_code,industry_name,parent_code,level")

    l1_by_code = {row["industry_code"]: clean_name(row["industry_name"]) for row in l1_rows}
    children = {name: [] for name in l1_by_code.values()}
    code_by_name = {}
    level_by_name = {}
    for row in l1_rows:
        name = clean_name(row["industry_name"])
        code_by_name[name] = row["index_code"]
        level_by_name[name] = 1
    for row in l2_rows:
        parent = l1_by_code.get(row["parent_code"])
        if not parent:
            continue
        name = clean_name(row["industry_name"])
        # A few SW names collide after removing level suffixes, e.g. L1/L2 "综合".
        # Keep the original L2 suffix in those cases so metrics are not overwritten.
        if name in code_by_name:
            name = row["industry_name"]
        children[parent].append(name)
        code_by_name[name] = row["index_code"]
        level_by_name[name] = 2

    metrics = {}
    fields = "ts_code,trade_date,name,close,pe,total_mv"
    items = list(code_by_name.items())
    for idx, (name, code) in enumerate(items, 1):
        print(f"[{idx}/{len(items)}] {name} {code}", flush=True)
        rows = call_api(
            token,
            "sw_daily",
            {"ts_code": code, "start_date": START_DATE, "end_date": END_DATE},
            fields,
        )
        metrics[name] = build_history(rows)
        time.sleep(0.08)

    # Sort using latest total market value, descending.
    sorted_industries = {}
    for parent in sorted(children, key=lambda n: (metrics.get(n, {}).get("latest", {}).get("totalMv") or 0), reverse=True):
        sorted_industries[parent] = sorted(
            children[parent],
            key=lambda n: (metrics.get(n, {}).get("latest", {}).get("totalMv") or 0),
            reverse=True,
        )

    payload = {
        "source": "Tushare sw_daily / index_classify, SW2021",
        "asOf": END_DATE,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "industries": sorted_industries,
        "codes": code_by_name,
        "levels": level_by_name,
        "metrics": metrics,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
