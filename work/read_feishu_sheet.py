import json
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT.parent / "sheet-https-my-feishu-cn-wiki" / ".env"
WIKI_TOKEN = "WlwpwV7pdiscWBkgutccXEkfnY9"
SHEET_ID = "JMiuVI"
OUTPUT = ROOT / "work" / "feishu_JMiuVI.json"


def load_env():
    values = {}
    for raw_line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def request(method, url, body=None, token=None):
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"{result.get('code')}: {result.get('msg')} ({url})")
    return result


def main():
    env = load_env()
    auth = request(
        "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]},
    )
    token = auth["tenant_access_token"]

    node = request(
        "GET",
        "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?"
        + urllib.parse.urlencode({"token": WIKI_TOKEN}),
        token=token,
    )
    spreadsheet_token = node["data"]["node"]["obj_token"]
    cell_range = f"{SHEET_ID}!A1:Z300"
    encoded_range = urllib.parse.quote(cell_range, safe="!")
    values = request(
        "GET",
        f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{encoded_range}",
        token=token,
    )["data"]["valueRange"].get("values", [])

    payload = {
        "wikiToken": WIKI_TOKEN,
        "sheetId": SHEET_ID,
        "spreadsheetToken": spreadsheet_token,
        "range": cell_range,
        "rows": values,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(values), "columns": max((len(r) for r in values), default=0), "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
