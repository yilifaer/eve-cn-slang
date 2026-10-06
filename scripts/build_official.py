"""从 CCP 官方静态数据（SDE）生成 official/eve-official.json 和 .csv（官方中英名称表）。

筛选规则和 koishi-plugin-dcqq-bridge 的 scripts/build-eve-glossary.mjs 一致（改规则时两边一起改）：
只收中英文名都有、而且两者不一样的；物品只收市场上有的舰船、装备、弹药等，不收涂装、蓝图、技能、服饰；
星系、星座、星域不收虫洞等特殊空间和代号名字。

中英文名称和仓库里的完全一样时不改任何文件（CCP 出了新版本、但新东西还没有中文名时就是这样）。
有变化时同时更新 README 里的条数和版本号。

用法：
    python scripts/build_official.py                       # 下载 CCP 最新的 SDE
    python scripts/build_official.py path/to/sde.zip       # 用下载好的 eve-online-static-data-<build>-jsonl.zip
    python scripts/build_official.py --summary changes.md  # 另外把变化写成 Markdown（每周自动检查开合并请求时用）
"""
import argparse, csv, io, json, re, shutil, tempfile, urllib.request, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SDE = "https://developers.eveonline.com/static-data/tranquility"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "official"
KINDS = ["category", "group", "type", "region", "constellation", "system"]
KIND_ZH = {"category": "大类", "group": "分组", "type": "物品", "region": "星域", "constellation": "星座", "system": "星系"}
# 收录物品的类别：材料、舰船、装备、弹药、商品、无人机、植入体、可部署物、星堡、小行星、子系统、建筑、建筑装备、铁骑
TYPE_CATEGORIES = {4, 6, 7, 8, 17, 18, 20, 22, 23, 25, 32, 65, 66, 87}
# 不收的类别：SKIN、蓝图、服饰、技能、特别版；「个性化」按名字找
EXCLUDED_CATEGORIES = {91, 9, 30, 16, 63}
CODE_NAME = re.compile(r"[A-Z0-9]{1,5}-[A-Z0-9]{1,5}")  # 代号星系（以及同样形式的星域、星座名）
WH_REGION_MIN, WH_CONSTELLATION_MIN = 11000000, 21000000  # 虫洞等特殊空间
SUMMARY_LIMIT = 200  # 合并请求说明里每张表最多列多少条（GitHub 限制说明长度）


def latest_build():
    with urllib.request.urlopen(f"{SDE}/latest.jsonl", timeout=60) as r:
        for line in r.read().decode("utf-8").splitlines():
            o = json.loads(line) if line.strip() else {}
            if o.get("_key") == "sde" and isinstance(o.get("buildNumber"), int):
                return o["buildNumber"]
    raise RuntimeError("latest.jsonl 里没有 buildNumber")


def download(build_no, dest):
    url = f"{SDE}/eve-online-static-data-{build_no}-jsonl.zip"
    print("下载", url)
    with urllib.request.urlopen(url, timeout=600) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def rows(zf, name):
    """逐行读取 zip 里的一个 JSONL 文件（types.jsonl 解压后一百多 MB，不整个读进内存）"""
    info = next((i for i in zf.infolist() if i.filename.rsplit("/", 1)[-1] == name), None)
    if info is None:
        raise RuntimeError(f"zip 里缺少 {name}")
    with zf.open(info) as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            if line.strip():
                yield json.loads(line)


def name(o, lang):
    n = (o.get("name") or {}).get(lang)
    return n.strip() if isinstance(n, str) else ""


def build(zip_path):
    entries = set()  # 用集合顺便去掉完全相同的条目

    def add(kind, o):
        en, zh = name(o, "en"), name(o, "zh")
        if en and zh and en != zh:
            entries.add((kind, en, zh))

    def is_code(o):
        return CODE_NAME.fullmatch(name(o, "en"))

    with zipfile.ZipFile(zip_path) as zf:
        build_no = next(o["buildNumber"] for o in rows(zf, "_sde.jsonl") if o.get("_key") == "sde")
        categories = list(rows(zf, "categories.jsonl"))
        excluded = EXCLUDED_CATEGORIES | {c["_key"] for c in categories if name(c, "en").lower() == "personalization"}
        for c in categories:
            if c.get("published") is True and c["_key"] not in excluded:
                add("category", c)
        group_category = {}
        for g in rows(zf, "groups.jsonl"):
            group_category[g["_key"]] = g.get("categoryID")
            if g.get("published") is True and g.get("categoryID") not in excluded:
                add("group", g)
        for t in rows(zf, "types.jsonl"):
            cat = group_category.get(t.get("groupID"))
            if t.get("published") is True and t.get("marketGroupID") is not None and cat in TYPE_CATEGORIES and cat not in excluded:
                add("type", t)
        for r in rows(zf, "mapRegions.jsonl"):
            if r["_key"] < WH_REGION_MIN and not is_code(r):
                add("region", r)
        for c in rows(zf, "mapConstellations.jsonl"):
            if c["_key"] < WH_CONSTELLATION_MIN and (c.get("regionID") or 0) < WH_REGION_MIN and not is_code(c):
                add("constellation", c)
        for s in rows(zf, "mapSolarSystems.jsonl"):
            if (s.get("regionID") or 0) < WH_REGION_MIN and not is_code(s):
                add("system", s)
    return build_no, sorted(entries, key=lambda e: (KINDS.index(e[0]), e[1].lower(), e[1], e[2]))


def write(build_no, entries):
    out = {
        "source": f"CCP hf. EVE Online Static Data Export (Tranquility), build {build_no}",
        "buildNumber": build_no,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "license": "EVE Developer License Agreement (non-commercial). NOT covered by CC BY 4.0. See official/NOTICE.md",
        "count": len(entries),
        "entries": [{"kind": k, "en": en, "zh": zh} for k, en, zh in entries],
    }
    (OUT / "eve-official.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    with open(OUT / "eve-official.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["kind", "en", "zh"])
        w.writerows(entries)


def update_readme(build_no, entries):
    p = ROOT / "README.md"
    s, c = p.read_text(encoding="utf-8"), Counter(k for k, _, _ in entries)
    n = lambda x: f"{x:,}"
    subs = [
        (r"\*\*[\d,]+ 条\*\* \| 从 CCP 静态数据生成（build \d+）", f"**{n(len(entries))} 条** | 从 CCP 静态数据生成（build {build_no}）"),
        (r"物品 [\d,]+，分组 [\d,]+，大类 [\d,]+，星系 [\d,]+，星座 [\d,]+，星域 [\d,]+",
         f"物品 {n(c['type'])}，分组 {n(c['group'])}，大类 {n(c['category'])}，星系 {n(c['system'])}，星座 {n(c['constellation'])}，星域 {n(c['region'])}"),
        (r"\*\*[\d,]+ official English/Chinese names\*\*", f"**{n(len(entries))} official English/Chinese names**"),
    ]
    for pattern, repl in subs:
        s, k = re.subn(pattern, repl, s)
        if not k:
            print("警告：README 里没找到要更新的数字：" + pattern)
    p.write_text(s, encoding="utf-8")


def changes(old, new):
    """按（类型, 英文名）对比：两边都有但中文不同算「中文名变化」，其余是新增或删除"""
    o, n = defaultdict(set), defaultdict(set)
    for k, en, zh in old:
        o[(k, en)].add(zh)
    for k, en, zh in new:
        n[(k, en)].add(zh)
    added, removed, changed = [], [], []
    for key in sorted(o.keys() | n.keys(), key=lambda x: (KINDS.index(x[0]), x[1].lower(), x[1])):
        a, b = " / ".join(sorted(o.get(key, ()))), " / ".join(sorted(n.get(key, ())))
        if a == b:
            continue
        if a and b:
            changed.append((*key, a, b))
        elif b:
            added.append((*key, b))
        else:
            removed.append((*key, a))
    return added, removed, changed


def summary(old_build, build_no, added, removed, changed):
    lines = [f"CCP 静态数据从 build {old_build} 更新到 build {build_no}：新增 {len(added)} 条，删除 {len(removed)} 条，中文名变化 {len(changed)} 条。", ""]
    cell = lambda x: x.replace("|", "\\|")

    def table(title, head, items):
        if not items:
            return
        lines.extend([f"### {title}（{len(items)}）", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)])
        lines.extend("| " + " | ".join([KIND_ZH[r[0]], *map(cell, r[1:])]) + " |" for r in items[:SUMMARY_LIMIT])
        if len(items) > SUMMARY_LIMIT:
            lines.extend(["", f"……还有 {len(items) - SUMMARY_LIMIT} 条，见文件改动"])
        lines.append("")

    table("新增", ["类型", "英文", "中文"], added)
    table("删除", ["类型", "英文", "中文"], removed)
    table("中文名变化", ["类型", "英文", "原来的中文", "现在的中文"], changed)
    lines.append("由每周自动检查（.github/workflows/update-official.yml）生成。看过没问题就点「Merge pull request」。")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="从 CCP 静态数据生成官方中英名称表")
    ap.add_argument("zip", nargs="?", help="下载好的 SDE 压缩包；不填就下载 CCP 最新的")
    ap.add_argument("--summary", help="有变化时把变化写成 Markdown 文件")
    args = ap.parse_args()

    cur = json.loads((OUT / "eve-official.json").read_text(encoding="utf-8"))
    old = [(e["kind"], e["en"], e["zh"]) for e in cur["entries"]]
    if args.zip:
        build_no, entries = build(args.zip)
    else:
        latest = latest_build()
        if latest == cur["buildNumber"]:
            print(f"仓库里已经是 CCP 最新的 build {latest}，不用更新")
            return
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "sde.zip"
            download(latest, zip_path)
            build_no, entries = build(zip_path)

    added, removed, changed = changes(old, entries)
    if not (added or removed or changed):
        print(f"CCP 的 build {build_no} 和仓库里的 build {cur['buildNumber']} 中英文名称完全一样，不用更新")
        return
    write(build_no, entries)
    update_readme(build_no, entries)
    print(f"已更新到 build {build_no}：新增 {len(added)}，删除 {len(removed)}，中文名变化 {len(changed)}；"
          f"共 {len(entries)} 条", dict(Counter(k for k, _, _ in entries)))
    if args.summary:
        Path(args.summary).write_text(summary(cur["buildNumber"], build_no, added, removed, changed), encoding="utf-8")


if __name__ == "__main__":
    main()
