"""把 EVE 官方中英名称表转换成本仓库的 official/eve-official.json 和 .csv。

数据来源：koishi-plugin-dcqq-bridge 的 data/eve-glossary.json，由它的
scripts/build-eve-glossary.mjs 从 CCP 静态数据（SDE）生成。

用法：
    python scripts/build_official.py                # 从 GitHub 下载最新的 eve-glossary.json
    python scripts/build_official.py path/to.json   # 用本地文件
"""
import csv, json, sys, urllib.request
from collections import Counter
from pathlib import Path

URL = "https://raw.githubusercontent.com/yilifaer/koishi-plugin-dcqq-bridge/main/data/eve-glossary.json"
ROOT = Path(__file__).resolve().parent.parent
KINDS = ["category", "group", "type", "region", "constellation", "system"]


def load(src):
    if src:
        return json.loads(Path(src).read_text(encoding="utf-8"))
    with urllib.request.urlopen(URL, timeout=60) as r:
        return json.load(r)


def main():
    data = load(sys.argv[1] if len(sys.argv) > 1 else None)
    entries = sorted(data["entries"], key=lambda e: (KINDS.index(e["kind"]) if e["kind"] in KINDS else 99, e["en"].lower()))
    out = {
        "source": "CCP hf. EVE Online Static Data Export (Tranquility), build %s" % data["buildNumber"],
        "buildNumber": data["buildNumber"],
        "generatedAt": data["generatedAt"],
        "license": "EVE Developer License Agreement (non-commercial). NOT covered by CC BY 4.0. See official/NOTICE.md",
        "count": len(entries),
        "entries": [{"kind": e["kind"], "en": e["en"], "zh": e["zh"]} for e in entries],
    }
    (ROOT / "official" / "eve-official.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    with open(ROOT / "official" / "eve-official.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "en", "zh"])
        for e in entries:
            w.writerow([e["kind"], e["en"], e["zh"]])
    print("build", data["buildNumber"], "entries", len(entries), dict(Counter(e["kind"] for e in entries)))


if __name__ == "__main__":
    main()
