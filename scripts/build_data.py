"""从 CCP 官方静态数据（SDE）生成插件数据 official/data/：manifest.json、types.json、industry.json、universe.json。

给 QQ 机器人插件（koishi-plugin-eve-market）在线读取，插件只轮询 manifest.json，有变化时三个数据文件一起下载：
- types.json：所有已发布的物品（带拼音列 py）、分组、大类、市场分组、元分组；
- industry.json：蓝图（制造 m、反应 r、发明 i）、Upwell 建筑的工业加成、工业改装件、目标过滤器；
- universe.json：星域、星座、星系（含虫洞空间）、NPC 空间站、势力、星门连接。

格式：开头是头部键，每个一行；表一行一条、按 id 排序。大部分表带列名数组（columns、groupColumns……），行是紧凑的 JSON 数组；
industry.json 的 structures、rigs、filters 是对象数组，一行一个对象。
插件按列名取值，所以加列不影响旧插件：加列、加表时把 DATA_REVISION 加 1；改列名、改含义这种不兼容的变化才把 SCHEMA 加 1。
整数写整数，其他数字保留 6 位小数；SDE 没有中文名、中文和英文一样或者是代号星系时 zh 写 ""。

内容和仓库里的一样时不改文件：比较时不看 generatedAt 和版本号（只有 build 号变了不算变化），只重写真正变了的文件，
有变化时 manifest 一起更新。所以各文件头部的 build 号可能比 manifest 旧，以 manifest 为准；
manifest 的 generatedAt 是内容上次变化的时间，不是上次检查的时间。内容没变、但格式和这里写出的不一样（例如换行符）的文件
按原来的头部重新写一遍。写文件之前先校验（引用完整、id 唯一有序、行数没有比仓库里少 20% 以上、文件不超过 10 MB），
有一条不过就失败，什么都不写。

用法：
    python scripts/build_data.py                         # 下载 CCP 最新的 SDE
    python scripts/build_data.py path/to/sde.zip         # 用下载好的 eve-online-static-data-<build>-jsonl.zip
    python scripts/build_data.py --save-zip sde.zip      # 下载的压缩包留下来，给 build_official.py 用（SDE 只下载一次）
    python scripts/build_data.py --summary changes.md    # 另外把变化写成 Markdown（每周自动检查时用）
    python scripts/build_data.py --check                 # 不联网，只校验仓库里已提交的文件
需要：pip install pypinyin==0.55.0（版本见 PYPINYIN_VERSION，和 update-official.yml 里的一致；只在生成时用，--check 只用标准库）
"""
import argparse, gzip, hashlib, json, os, re, sys, tempfile, unicodedata, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations, islice, product
from pathlib import Path

from build_official import CODE_NAME, ROOT, download, latest_build, name, rows

OUT = ROOT / "official" / "data"
SCHEMA = 1  # 不兼容的变化（改列名、改含义）才加 1
DATA_REVISION = 1  # 生成规则的版本：SDE 没变、但这里加了列或表时加 1，插件才会换掉缓存里缺列的旧文件
LICENSE = "EVE Developer License Agreement (non-commercial). NOT covered by CC BY 4.0. See official/NOTICE.md"
MAX_BYTES = 10 * 1024 * 1024  # 任何文件超过 10 MB 就失败（jsDelivr 单文件限制约 20 MB）
MIN_RATIO = 0.8  # 任何一张表的行数比仓库里少 20% 以上就失败（防止 SDE 出问题）
SUMMARY_LIMIT = 50  # 变化说明里每类最多列多少条例子
PY_MAX = 4  # 拼音列最多几种读法组合
PYPINYIN_VERSION = "0.55.0"  # 拼音库换版本会改拼音列；要升级时这里和 update-official.yml 一起改

# 每个文件里的表：表名 → (列名数组的键, 列名)；列名是 None 的表是对象数组（一行一个对象）
TABLES = {
    "types.json": {
        "types": ("columns", ["id", "en", "zh", "group", "marketGroup", "metaGroup", "techLevel", "volume",
                              "packagedVolume", "portionSize", "variationParent", "capacity", "py"]),
        "groups": ("groupColumns", ["id", "category", "en", "zh", "published"]),
        "categories": ("categoryColumns", ["id", "en", "zh", "published"]),
        "marketGroups": ("marketGroupColumns", ["id", "parent", "en", "zh"]),
        "metaGroups": ("metaGroupColumns", ["id", "en", "zh"]),
    },
    "industry.json": {
        "blueprints": ("blueprintColumns", ["blueprint", "activity", "time", "maxRuns", "products", "materials"]),
        "structures": (None, None),
        "rigs": (None, None),
        "filters": (None, None),
    },
    "universe.json": {
        "regions": ("regionColumns", ["id", "en", "zh"]),
        "constellations": ("constellationColumns", ["id", "region", "en", "zh"]),
        "systems": ("systemColumns", ["id", "constellation", "region", "security", "en", "zh"]),
        "stations": ("stationColumns", ["id", "system"]),
        "factions": ("factionColumns", ["id", "en", "zh"]),
        "jumps": ("jumpColumns", ["a", "b"]),
    },
}
MAIN_TABLE = {"types.json": "types", "industry.json": "blueprints", "universe.json": "systems"}  # manifest 里的 rows
TABLE_ZH = {"groups": "分组", "categories": "大类", "marketGroups": "市场分组", "metaGroups": "元分组", "structures": "建筑",
            "rigs": "改装件", "filters": "过滤器", "regions": "星域", "constellations": "星座", "stations": "空间站",
            "factions": "势力", "jumps": "星门连接"}
KEY_WIDTH = {"blueprints": 2, "jumps": 2}  # 这两张表按前两列排序、检查唯一，其他表按第一列（id）
KEY_TYPES = {"blueprints": (int, str), "jumps": (int, int)}  # 排序用的列的类型，其他表的 id 是整数
HEADER = ["schema", "buildNumber", "sdeReleaseDate", "source", "license", "generatedAt"]
VOLATILE = {"generatedAt", "buildNumber", "sdeReleaseDate", "source"}  # 比较内容时不看

# 工业活动的代号；蓝图只收制造、反应、发明（拷贝和研究不收）
ACTIVITIES = {"manufacturing": "m", "reaction": "r", "invention": "i", "copying": "c", "researchMaterial": "rm", "researchTime": "rt"}
ACT_ORDER = list(ACTIVITIES.values())
ACT_ZH = {"m": "制造", "r": "反应", "i": "发明"}
BLUEPRINT_ACTIVITIES = {"manufacturing": "m", "reaction": "r", "invention": "i"}
MODIFIER_KINDS = {"material": "me", "time": "te", "cost": "cost"}
KIND_ORDER = ["me", "te", "cost"]
STRUCTURE_GROUPS = {1404, 1406, 1657}  # 工程复合体、精炼厂、堡垒
RIG_CATEGORY, OUTPOST_RIG_GROUP = 66, 1984  # 建筑装备；Upwell 前哨改装件用另一套属性，不收
# dogma 属性 ID 对照表（数据层的知识，插件里不需要）
ATTR_RIG_SIZE, ATTR_NO_HIGHSEC = 1547, 1970
STRUCTURE_ATTRS = {2600: "me", 2601: "cost", 2602: "te", 2721: "te"}  # 建筑加成（乘数）；2721 是反应时间
RIG_SEC_ATTRS = {"h": 2355, "l": 2356, "n": 2357}  # 高安、低安、00 的倍数；没有这个属性写 null，表示这里不生效
OP_POST_PERCENT = 6  # dogma 效果的运算：按百分比加成（改装件的加成都是这种）
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")  # 汉字
PY_TOKEN = re.compile(r"[a-z0-9]+")


def num(x):
    """整数写整数，其他保留 6 位小数"""
    if x is None or isinstance(x, (bool, int)):
        return x
    r = round(float(x), 6)
    return int(r) if r.is_integer() else r


def zh_of(o):
    """中文名；没有或者和英文一样时是空字符串"""
    zh = name(o, "zh")
    return "" if zh == name(o, "en") else zh


def map_zh(o):
    """星域、星座、星系的中文名；代号名字（例如 YM-SRU）是空字符串，SDE 里有几个是截短的英文"""
    return "" if CODE_NAME.fullmatch(name(o, "en")) else zh_of(o)


def pinyin_maker():
    """返回 中文名 → py 列的函数：每种读法一对「全拼 首字母」，空格隔开（第 1、3……个是全拼，第 2、4……个是首字母）。
    多音字：拼音库按词语给出唯一读法时只用那个；单字有几种读法时，留下拼音库的首选读法，
    以及在拼音库词库里占这个字 10% 以上的读法，词库里常见的在前（「长」→ chang、zhang），
    生僻读法不占 4 种组合的名额。组合先换一个字的读法，再换两个……"""
    import pypinyin
    from pypinyin import Style, pinyin
    from pypinyin.contrib.tone_convert import to_normal
    from pypinyin.phrases_dict import phrases_dict

    if pypinyin.__version__ != PYPINYIN_VERSION:
        raise SystemExit(f"拼音库是 {pypinyin.__version__}，要用 {PYPINYIN_VERSION}（pip install pypinyin=={PYPINYIN_VERSION}），"
                         "不然拼音列会和每周自动生成的不一样")

    freq = defaultdict(Counter)
    for phrase, readings in phrases_dict.items():
        if len(phrase) == len(readings):
            for ch, r in zip(phrase, readings):
                freq[ch][to_normal(r[0])] += 1

    def latin(s):  # 拉丁字母和数字原样（小写）保留，其他符号去掉
        t = re.sub(r"[^a-z0-9]", "", s.lower())
        return [([t], False)] if t else []

    def syllables(zh):
        """[(候选读法, 是不是汉字)]"""
        out, pos = [], 0
        for m in HAN.finditer(zh):
            out += latin(zh[pos:m.start()])
            run = m.group()
            res = pinyin(run, style=Style.NORMAL, heteronym=True)
            if len(res) != len(run):  # 有拼音库不认识的字时逐字查
                res = [pinyin(ch, style=Style.NORMAL, heteronym=True)[0] for ch in run]
            for ch, cands in zip(run, res):
                cands = [c for c in cands if re.fullmatch("[a-z]+", c)]
                if len(cands) > 1:
                    # 第一个是拼音库的首选读法，一定留下（「莎」在词库里只有「莎草」suo，但音译名里读 sha）
                    f = freq[ch]
                    total = sum(f.values())
                    cands = sorted(cands[:1] + [c for c in cands[1:] if f[c] and f[c] * 10 >= total], key=lambda c: -f[c])
                if cands:
                    out.append((cands, True))
            pos = m.end()
        return out + latin(zh[pos:])

    def py(zh):
        parts = syllables(unicodedata.normalize("NFKC", zh))
        if not any(han for _, han in parts):
            return None
        base = [c[0] for c, _ in parts]
        multi = [i for i, (c, _) in enumerate(parts) if len(c) > 1]

        def variants():
            yield base
            for k in range(1, len(multi) + 1):
                for pos in combinations(multi, k):
                    for alt in product(*(parts[i][0][1:] for i in pos)):
                        v = list(base)
                        for i, r in zip(pos, alt):
                            v[i] = r
                        yield v

        pairs = []  # 首字母一样也要写，插件按位置区分全拼和首字母
        for v in islice(variants(), PY_MAX):
            pair = ("".join(v), "".join(s[0] if han else s for s, (_, han) in zip(v, parts)))
            if pair not in pairs:
                pairs.append(pair)
        return " ".join(t for pair in pairs for t in pair)

    return py


def build(zip_path):
    """读 SDE，返回 (三个数据文件的内容, 丢掉的蓝图)"""
    py = pinyin_maker()
    with zipfile.ZipFile(zip_path) as zf:
        sde = next(o for o in rows(zf, "_sde.jsonl") if o.get("_key") == "sde")
        build_no, release = sde["buildNumber"], sde.get("releaseDate", "")
        categories = list(rows(zf, "categories.jsonl"))
        groups = list(rows(zf, "groups.jsonl"))
        market_groups = list(rows(zf, "marketGroups.jsonl"))
        meta_groups = list(rows(zf, "metaGroups.jsonl"))
        group_category = {g["_key"]: g.get("categoryID") for g in groups}

        types, published = {}, set()
        for t in rows(zf, "types.jsonl"):
            if t.get("published") is not True:
                continue
            published.add(t["_key"])
            en, zh = name(t, "en"), zh_of(t)
            vol, pvol = num(t.get("volume")), num(t.get("packagedVolume"))
            market = t.get("marketGroupID")
            types[t["_key"]] = [t["_key"], en, zh, t.get("groupID"), market, t.get("metaGroupID"), t.get("techLevel"),
                                vol, None if pvol == vol else pvol, t.get("portionSize"), t.get("variationParentTypeID"),
                                num(t.get("capacity")) or None, py(zh) if market is not None and zh else None]

        # 蓝图：只收已发布的蓝图；产品都没发布的不收；产品发布了、但材料或别的产品没发布的丢掉这一行并写进说明
        blueprints, dropped = [], []
        for b in rows(zf, "blueprints.jsonl"):
            if b["_key"] not in published:
                continue
            for act, code in BLUEPRINT_ACTIVITIES.items():
                a = (b.get("activities") or {}).get(act) or {}
                products = [[p["typeID"], p["quantity"], *([num(p["probability"])] if "probability" in p else [])] for p in a.get("products", [])]
                materials = [[m["typeID"], m["quantity"]] for m in a.get("materials", [])]
                if not any(p[0] in published for p in products):
                    continue
                missing = sorted({x[0] for x in products + materials} - published)
                if missing:
                    dropped.append((b["_key"], code, missing))
                    continue
                blueprints.append([b["_key"], code, a.get("time", 0), b.get("maxProductionLimit"), products, materials])

        modifiers = {m["_key"]: m for m in rows(zf, "industryModifierSources.jsonl")}
        structure_ids = sorted(k for k, t in types.items() if t[3] in STRUCTURE_GROUPS)
        rig_ids = sorted(k for k in modifiers if k in types and group_category.get(types[k][3]) == RIG_CATEGORY and types[k][3] != OUTPOST_RIG_GROUP)
        need = set(structure_ids) | set(rig_ids)
        dogma, rig_effect_ids = {}, {}
        for d in rows(zf, "typeDogma.jsonl"):
            if d["_key"] in need:
                dogma[d["_key"]] = {a["attributeID"]: a["value"] for a in d.get("dogmaAttributes", [])}
                if d["_key"] in rig_ids:
                    rig_effect_ids[d["_key"]] = [e["effectID"] for e in d.get("dogmaEffects", [])]
        # 改装件的 dogma 效果：改的建筑属性 → 改装件上提供数值的属性
        # （只看作用在建筑上、按百分比加成的）
        wanted = {e for es in rig_effect_ids.values() for e in es}
        effect_attrs = {e["_key"]: [(m["modifiedAttributeID"], m["modifyingAttributeID"]) for m in e.get("modifierInfo") or []
                                    if m.get("domain") == "structureID" and m.get("operation") == OP_POST_PERCENT]
                        for e in rows(zf, "dogmaEffects.jsonl") if e["_key"] in wanted}
        filters = [{"id": f["_key"], "name": f["name"] if isinstance(f.get("name"), str) else name(f, "en"),
                    "categories": sorted(f.get("categoryIDs", [])), "groups": sorted(f.get("groupIDs", []))}
                   for f in rows(zf, "industryTargetFilters.jsonl")]

        regions = [[r["_key"], name(r, "en"), map_zh(r)] for r in rows(zf, "mapRegions.jsonl")]
        constellations = [[c["_key"], c.get("regionID"), name(c, "en"), map_zh(c)] for c in rows(zf, "mapConstellations.jsonl")]
        systems = [[s["_key"], s.get("constellationID"), s.get("regionID"), num(s.get("securityStatus")), name(s, "en"), map_zh(s)]
                   for s in rows(zf, "mapSolarSystems.jsonl")]
        stations = [[s["_key"], s.get("solarSystemID")] for s in rows(zf, "npcStations.jsonl")]
        factions = [[f["_key"], name(f, "en"), zh_of(f)] for f in rows(zf, "factions.jsonl")]
        jumps = {tuple(sorted((g["solarSystemID"], g["destination"]["solarSystemID"]))) for g in rows(zf, "mapStargates.jsonl")}

    structures, rigs = [], []
    for k in structure_ids:
        d, bonus = dogma.get(k, {}), {}
        for act, kinds in sorted(effects_of(modifiers.get(k)).items(), key=lambda x: ACT_ORDER.index(x[0])):
            for kind, attrs in kinds.items():
                for attr in attrs:
                    if STRUCTURE_ATTRS.get(attr) != kind or attr not in d:
                        raise SystemExit(f"建筑 {k} 的 {act}/{kind} 用了属性 {attr}，不在对照表里或者建筑没有这个属性，先核实再改 STRUCTURE_ATTRS")
                    bonus.setdefault(act, {})[kind] = num(d[attr])
        structures.append({"id": k, "en": types[k][1], "zh": types[k][2], "group": types[k][3], "rigSize": num(d.get(ATTR_RIG_SIZE)),
                           "highsec": not d.get(ATTR_NO_HIGHSEC), "bonus": {a: {x: b[x] for x in KIND_ORDER if x in b} for a, b in bonus.items()}})
    for k in rig_ids:
        # 每条加成的百分比顺着 dogma 效果找：修正来源里的建筑属性 → 改装件的哪个属性给它加成。
        # 同一个改装件对不同产品的加成可能不一样：Thukker 改装件对旗舰组件的材料加成用属性 2653，
        # 对其他产品用 2594
        d, source = dogma.get(k, {}), {}
        for e in rig_effect_ids.get(k, []):
            source.update(effect_attrs.get(e, []))
        effects = {}
        for act, kinds in effects_of(modifiers[k]).items():
            for kind, fs in kinds.items():
                for attr, f in fs.items():
                    if source.get(attr) not in d:
                        raise SystemExit(f"改装件 {k} 的 {act}/{kind}（建筑属性 {attr}）找不到按百分比加成的 dogma 效果，先核实")
                    if (act, kind, f) in effects:
                        raise SystemExit(f"改装件 {k} 的 {act}/{kind} 对过滤器 {f} 有两条加成，先核实")
                    effects[act, kind, f] = num(d[source[attr]])
        rigs.append({"id": k, "en": types[k][1], "zh": types[k][2], "group": types[k][3], "size": num(d.get(ATTR_RIG_SIZE)),
                     "sec": {s: num(d.get(a)) for s, a in RIG_SEC_ATTRS.items()},
                     "effects": [[*e, v] for e, v in sorted(effects.items(), key=lambda x: effect_key(x[0]))]})

    head = {"schema": SCHEMA, "buildNumber": build_no, "sdeReleaseDate": release,
            "source": f"CCP hf. EVE Online Static Data Export (Tranquility), build {build_no}", "license": LICENSE,
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")}
    tables = {
        "types.json": {
            "types": list(types.values()),
            "groups": [[g["_key"], g.get("categoryID"), name(g, "en"), zh_of(g), g.get("published") is True] for g in groups],
            "categories": [[c["_key"], name(c, "en"), zh_of(c), c.get("published") is True] for c in categories],
            "marketGroups": [[m["_key"], m.get("parentGroupID"), name(m, "en"), zh_of(m)] for m in market_groups],
            "metaGroups": [[m["_key"], name(m, "en"), zh_of(m)] for m in meta_groups],
        },
        "industry.json": {"blueprints": blueprints, "structures": structures, "rigs": rigs, "filters": filters},
        "universe.json": {"regions": regions, "constellations": constellations, "systems": systems, "stations": stations,
                          "factions": factions, "jumps": [list(j) for j in jumps]},
    }
    docs = {}
    for f, tabs in tables.items():
        doc = dict(head)
        for t, (col_key, cols) in TABLES[f].items():
            if col_key:
                doc[col_key] = cols
            doc[t] = sorted(tabs[t], key=lambda r, t=t: row_key(t, r))
        docs[f] = doc
    return docs, dropped


def effects_of(mod):
    """industryModifierSources 的一条 → {活动代号: {种类: {属性ID: 过滤器ID 或 None}}}"""
    out = {}
    for act, kinds in (mod or {}).items():
        if act == "_key":
            continue
        for kind, entries in kinds.items():
            for e in entries:
                out.setdefault(ACTIVITIES[act], {}).setdefault(MODIFIER_KINDS[kind], {})[e["dogmaAttributeID"]] = e.get("filterID")
    return out


def effect_key(e):
    """改装件 effects 的排序：活动、种类、过滤器（null 在前）"""
    return ACT_ORDER.index(e[0]), KIND_ORDER.index(e[1]), -1 if e[2] is None else e[2]


def row_key(table, r):
    if isinstance(r, dict):
        return (r.get("id"),)
    return tuple(r[:KEY_WIDTH.get(table, 1)])


def dump(doc):
    """头部键每个一行；表一行一条（看差异清楚）；manifest 的 files 一个文件一行"""
    c = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    out = []
    for k, v in doc.items():
        if isinstance(v, list) and v and isinstance(v[0], (list, dict)):
            out.append(f"{c(k)}: [\n" + ",\n".join(c(r) for r in v) + "\n]")
        elif isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
            out.append(f"{c(k)}: {{\n" + ",\n".join(f"{c(a)}: {c(b)}" for a, b in v.items()) + "\n}")
        else:
            out.append(f"{c(k)}: {c(v)}")
    return "{\n" + ",\n".join(out) + "\n}\n"


def stable(doc):
    """去掉 generatedAt 和版本号，用来比较内容有没有变"""
    return {k: v for k, v in doc.items() if k not in VOLATILE}


def bad_numbers(v):
    """整数写成了小数、或者超过 6 位小数的数字"""
    if isinstance(v, float):
        return v.is_integer() or round(v, 6) != v
    if isinstance(v, list):
        return any(bad_numbers(x) for x in v)
    if isinstance(v, dict):
        return any(bad_numbers(x) for x in v.values())
    return False


def validate(docs):
    """返回三个数据文件里的错误（格式、排序、引用完整）"""
    errors = []
    err = errors.append
    for f, tabs in TABLES.items():
        doc = docs.get(f)
        if not isinstance(doc, dict):
            err(f"{f}：没有内容")
            continue
        if list(doc)[:len(HEADER)] != HEADER:
            err(f"{f}：头部键应该是 {HEADER}")
        if doc.get("schema") != SCHEMA or not isinstance(doc.get("buildNumber"), int):
            err(f"{f}：schema 或 buildNumber 不对")
        for t, (col_key, cols) in tabs.items():
            rs = doc.get(t)
            if not isinstance(rs, list):
                err(f"{f}：缺少表 {t}")
                continue
            if col_key:
                if doc.get(col_key) != cols:
                    err(f"{f}：{col_key} 应该是 {cols}")
                bad = [r for r in rs if not isinstance(r, list) or len(r) != len(cols)
                       or not all(type(x) is c for x, c in zip(row_key(t, r), KEY_TYPES.get(t, (int,))))]
            else:
                bad = [r for r in rs if not isinstance(r, dict) or type(r.get("id")) is not int]
            if bad:
                err(f"{f}：{t} 有 {len(bad)} 行格式不对，例如 {str(bad[0])[:200]}")
                continue
            keys = [row_key(t, r) for r in rs]
            wrong = next((i for i in range(1, len(keys)) if not keys[i - 1] < keys[i]), None)
            if wrong is not None:
                err(f"{f}：{t} 的 id 有重复或没排序：{keys[wrong - 1]} 后面是 {keys[wrong]}")
            if bad_numbers(rs):
                err(f"{f}：{t} 里有整数写成了小数，或者超过 6 位小数的数字")
            if col_key and "en" in cols and "zh" in cols:
                ie, iz = cols.index("en"), cols.index("zh")
                same = [r[0] for r in rs if r[iz] and r[iz] == r[ie]]
                if same:
                    err(f"{f}：{t} 有 {len(same)} 行中文和英文一样，应该写 \"\"，例如 {same[:5]}")
    if errors:
        return errors

    ty, ind, uni = docs["types.json"], docs["industry.json"], docs["universe.json"]
    ints = lambda v, n: isinstance(v, list) and len(v) >= n and all(type(x) is int for x in v[:n])
    number = lambda x: type(x) in (int, float)
    shapes = [
        ("蓝图的 products、materials 应该是 [[typeID, 数量], ...]",
         [r[:2] for r in ind["blueprints"] if not all(isinstance(r[i], list) and all(ints(x, 2) for x in r[i]) for i in (4, 5))]),
        ("建筑的 bonus 应该是 {活动: {种类: 数字}}",
         [s["id"] for s in ind["structures"] if not (isinstance(s.get("bonus"), dict) and all(
             a in ACT_ORDER and isinstance(b, dict) and all(k in KIND_ORDER and number(v) for k, v in b.items()) for a, b in s["bonus"].items()))]),
        ("改装件的 sec 应该是 {h, l, n: 数字或 null}",
         [s["id"] for s in ind["rigs"] if not (isinstance(s.get("sec"), dict) and set(s["sec"]) == set(RIG_SEC_ATTRS)
                                              and all(v is None or number(v) for v in s["sec"].values()))]),
        ("改装件的 effects 应该是 [[活动, 种类, 过滤器 id 或 null, 百分比], ...]，按活动、种类、过滤器排序",
         [s["id"] for s in ind["rigs"] if not (isinstance(s.get("effects"), list) and s["effects"] and all(
             isinstance(e, list) and len(e) == 4 and e[0] in ACT_ORDER and e[1] in KIND_ORDER
             and (e[2] is None or type(e[2]) is int) and number(e[3]) for e in s["effects"])
             and all(effect_key(a) < effect_key(b) for a, b in zip(s["effects"], s["effects"][1:])))]),
        ("过滤器的 categories、groups 应该是整数数组",
         [x["id"] for x in ind["filters"]
          if not all(isinstance(x.get(k), list) and all(type(v) is int for v in x[k]) for k in ("categories", "groups"))]),
    ]
    for what, bad in shapes:
        if bad:
            err(f"industry.json：{what}，有 {len(bad)} 行不对，例如 {bad[:5]}")
    if errors:
        return errors

    type_ids = {r[0] for r in ty["types"]}
    group_ids, category_ids = {r[0] for r in ty["groups"]}, {r[0] for r in ty["categories"]}
    market_ids, meta_ids = {r[0] for r in ty["marketGroups"]}, {r[0] for r in ty["metaGroups"]}
    filter_ids = {f["id"] for f in ind["filters"]}

    def refs(where, values, ids, nullable=True):
        missing = sorted({v for v in values if not (v is None and nullable) and v not in ids}, key=str)
        if missing:
            err(f"{where}：有 {len(missing)} 个引用找不到，例如 {missing[:10]}")

    refs("物品的分组", (r[3] for r in ty["types"]), group_ids, False)
    refs("物品的市场分组", (r[4] for r in ty["types"]), market_ids)
    refs("物品的元分组", (r[5] for r in ty["types"]), meta_ids)
    refs("物品的基础型号（variationParent）", (r[10] for r in ty["types"]), type_ids)
    refs("分组的大类", (r[1] for r in ty["groups"]), category_ids, False)
    refs("市场分组的上级", (r[1] for r in ty["marketGroups"]), market_ids)
    for r in ty["types"]:
        p = r[12]
        if p is not None and (r[4] is None or not r[2] or not isinstance(p, str) or len(p.split(" ")) % 2
                              or not all(PY_TOKEN.fullmatch(x) for x in p.split(" "))):
            err(f"物品 {r[0]} 的 py「{p}」不对：只给能上市场、有中文名的物品写，小写字母和数字，「全拼 首字母」成对、空格隔开")
            break

    refs("蓝图本身", (r[0] for r in ind["blueprints"]), type_ids, False)
    refs("蓝图的产品", (p[0] for r in ind["blueprints"] for p in r[4]), type_ids, False)
    refs("蓝图的材料", (m[0] for r in ind["blueprints"] for m in r[5]), type_ids, False)
    if any(r[1] not in BLUEPRINT_ACTIVITIES.values() or not r[4] for r in ind["blueprints"]):
        err("蓝图：活动只能是 m / r / i，而且要有产品")
    refs("建筑", (s["id"] for s in ind["structures"]), type_ids, False)
    refs("改装件", (s["id"] for s in ind["rigs"]), type_ids, False)
    refs("改装件 effects 的过滤器", (e[2] for s in ind["rigs"] for e in s.get("effects", [])), filter_ids)
    refs("过滤器的大类", (c for f in ind["filters"] for c in f["categories"]), category_ids, False)
    refs("过滤器的分组", (g for f in ind["filters"] for g in f["groups"]), group_ids, False)

    region_ids, system_ids = {r[0] for r in uni["regions"]}, {r[0] for r in uni["systems"]}
    con_region = {r[0]: r[1] for r in uni["constellations"]}
    refs("星座的星域", con_region.values(), region_ids, False)
    refs("星系的星座", (r[1] for r in uni["systems"]), con_region, False)
    refs("星系的星域", (r[2] for r in uni["systems"]), region_ids, False)
    mismatch = [r[0] for r in uni["systems"] if r[1] in con_region and con_region[r[1]] != r[2]]
    if mismatch:
        err(f"星系的星域和所在星座的星域不一致，例如 {mismatch[:10]}")
    refs("空间站的星系", (r[1] for r in uni["stations"]), system_ids, False)
    refs("星门连接的星系", (x for r in uni["jumps"] for x in r), system_ids, False)
    if any(a >= b for a, b in uni["jumps"]):
        err("星门连接：每条要写成 a < b")
    return errors


def load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def check():
    """不联网校验 official/data/ 里已提交的文件，返回退出码"""
    docs, errors = {}, []
    manifest = load(OUT / "manifest.json")
    if not isinstance(manifest, dict):
        errors.append("缺少 official/data/manifest.json，或者不是合法的 JSON")
        manifest = {}
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("dataRevision"), int) or not isinstance(manifest.get("buildNumber"), int):
        errors.append("manifest：schema、dataRevision 或 buildNumber 不对")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(TABLES) or not all(isinstance(m, dict) for m in files.values()):
        errors.append(f"manifest：files 应该正好是 {sorted(TABLES)}，每个是 {{sha256, bytes, rows}}")
        files = {}
    for f in TABLES:
        p = OUT / f
        if not p.exists():
            errors.append(f"缺少 official/data/{f}")
            continue
        raw = p.read_bytes()
        try:
            doc = json.loads(raw.decode("utf-8"))
        except ValueError as e:
            errors.append(f"{f}：不是合法的 JSON：{e}")
            continue
        if not isinstance(doc, dict):
            errors.append(f"{f}：应该是一个 JSON 对象")
            continue
        docs[f] = doc
        if len(raw) > MAX_BYTES:
            errors.append(f"{f}：{len(raw):,} 字节，超过 10 MB")
        if dump(doc).encode("utf-8") != raw:
            errors.append(f"{f}：格式和生成脚本写出的不一样（头部键每个一行、表一行一条、紧凑写法、换行符是 LF），"
                          "请用 build_data.py 重新生成（内容没变时只按原来的头部重写格式）")
        m = files.get(f) or {}
        rows_ = doc.get(MAIN_TABLE[f])
        if m.get("sha256") != hashlib.sha256(raw).hexdigest() or m.get("bytes") != len(raw):
            errors.append(f"{f}：sha256 或 bytes 和 manifest 里的不一致")
        if not isinstance(rows_, list) or m.get("rows") != len(rows_):
            errors.append(f"{f}：manifest 里的 rows 是 {m.get('rows')}，实际有 {len(rows_) if isinstance(rows_, list) else '?'} 行")
        b, mb = doc.get("buildNumber"), manifest.get("buildNumber")
        if isinstance(b, int) and isinstance(mb, int) and b > mb:
            errors.append(f"{f}：头部的 buildNumber {b} 比 manifest 的 {mb} 新（manifest 的 build 号不能比数据文件旧）")
    if manifest and dump(manifest).encode("utf-8") != (OUT / "manifest.json").read_bytes():
        errors.append("manifest.json：格式和生成脚本写出的不一样")
    if len(docs) == len(TABLES):
        try:
            errors += validate(docs)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as e:  # 结构太乱，上面的检查没拦住
            errors.append(f"数据结构不对，校验时出错：{type(e).__name__}: {e}")
    for e in errors:
        print("错误：" + e)
    if not errors:
        print(f"插件数据检查通过（build {manifest['buildNumber']}，dataRevision {manifest['dataRevision']}）：" + "，".join(
            f"{f} {files[f]['rows']:,} 行 {files[f]['bytes'] / 1024 / 1024:.2f} MB" for f in TABLES))
    return 1 if errors else 0


def diff(old, new, table):
    """按 id 对比一张表：(新增, 删除, 变化) 的 (旧行, 新行) 列表"""
    o = {row_key(table, r): r for r in (old or {}).get(table) or []}
    n = {row_key(table, r): r for r in new.get(table) or []}
    added = [(None, n[k]) for k in sorted(n.keys() - o.keys())]
    removed = [(o[k], None) for k in sorted(o.keys() - n.keys())]
    changed = [(o[k], n[k]) for k in sorted(o.keys() & n.keys()) if o[k] != n[k]]
    return added, removed, changed


def changes_of(cols, o, n):
    """修改的行变了哪些列，例如「zh 吉塔 → 吉他」；products、materials 按 typeID 列出变化，最多 5 处"""
    s = lambda v: "无" if v is None else '""' if v == "" else ", ".join(map(str, v)) if isinstance(v, list) else str(v)
    out = []
    for col, a, b in zip(cols, o, n):
        if a == b:
            continue
        if isinstance(a, list) and isinstance(b, list):
            x, y = {r[0]: r[1:] for r in a}, {r[0]: r[1:] for r in b}
            d = [f"{k} {s(x.get(k))} → {s(y.get(k))}" for k in sorted(x.keys() | y.keys()) if x.get(k) != y.get(k)]
            out.append(f"{col}：" + "，".join(d[:5]) + (f"……共 {len(d)} 处" if len(d) > 5 else ""))
        else:
            out.append(f"{col} {s(a)} → {s(b)}")
    return "；".join(out)


def summary(old, new, old_build, dropped):
    """变化说明（Markdown）"""
    ty_new = {r[0]: r for r in new["types.json"]["types"]}
    ty_old = {r[0]: r for r in ((old.get("types.json") or {}).get("types") or [])}
    label = lambda r: " / ".join(x for x in (r[1], r[2]) if x) if r else ""
    cell = lambda x: str(x).replace("|", "\\|")
    vol = lambda r: f"{r[7]}" + (f"（打包 {r[8]}）" if r[8] is not None else "")
    new_build = new["types.json"]["buildNumber"]
    head = f"CCP 静态数据从 build {old_build} 更新到 build {new_build}" if old_build and old_build != new_build else f"CCP 静态数据 build {new_build}"
    lines, sections = ["## 插件数据（official/data/）", ""], []

    def table(title, head_, items):
        if not items:
            return
        sections.extend([f"### {title}（{len(items)}）", "", "| " + " | ".join(head_) + " |", "|" + "---|" * len(head_)])
        sections.extend("| " + " | ".join(map(cell, r)) + " |" for r in items[:SUMMARY_LIMIT])
        if len(items) > SUMMARY_LIMIT:
            sections.extend(["", f"……还有 {len(items) - SUMMARY_LIMIT} 条，见文件改动"])
        sections.append("")

    if "types.json" not in old:
        counts = "，".join(f"{f} {len(new[f][MAIN_TABLE[f]]):,} 行" for f in TABLES)
        lines.append(f"{head}：首次生成插件数据（{counts}）。")
    else:
        added, removed, changed = diff(old["types.json"], new["types.json"], "types")
        renamed = [(o, n) for o, n in changed if o[1:3] != n[1:3]]
        volume = [(o, n) for o, n in changed if o[7:9] != n[7:9]]
        bp = diff(old.get("industry.json"), new["industry.json"], "blueprints")
        sy = diff(old.get("universe.json"), new["universe.json"], "systems")
        n_bp, n_sy = sum(map(len, bp)), sum(map(len, sy))
        others = sum(1 for o, n in changed if o[1:3] == n[1:3] and o[7:9] == n[7:9])  # 分组、拼音等其他列
        lines.append(f"{head}：物品新增 {len(added)}，删除 {len(removed)}，改名 {len(renamed)}，体积变化 {len(volume)}，"
                     f"其他列变化 {others}；蓝图变化 {n_bp}；星系变化 {n_sy}。")
        table("物品新增", ["typeID", "名称"], [(n[0], label(n)) for _, n in added])
        table("物品删除", ["typeID", "名称"], [(o[0], label(o)) for o, _ in removed])
        table("物品改名", ["typeID", "原来的名称", "现在的名称"], [(n[0], label(o), label(n)) for o, n in renamed])
        table("体积变化", ["typeID", "名称", "原来的体积（m³）", "现在的体积（m³）"], [(n[0], label(n), vol(o), vol(n)) for o, n in volume])
        def each(d, cols):  # [(行, 变化)]；修改的行写出变了什么
            return ([(n, "新增") for _, n in d[0]] + [(o, "删除") for o, _ in d[1]]
                    + [(n, "修改：" + changes_of(cols, o, n)) for o, n in d[2]])

        table("蓝图变化", ["蓝图", "活动", "变化"], [(label(ty_new.get(r[0]) or ty_old.get(r[0])) or r[0], ACT_ZH[r[1]], what)
                                              for r, what in each(bp, TABLES["industry.json"]["blueprints"][1])])
        table("星系变化", ["星系ID", "名称", "变化"], [(r[0], " / ".join(x for x in (r[4], r[5]) if x), what)
                                              for r, what in each(sy, TABLES["universe.json"]["systems"][1])])
        other = []
        for f, tabs in TABLES.items():
            for t in tabs:
                if t == MAIN_TABLE[f]:
                    continue
                d = diff(old.get(f), new[f], t)
                if any(d):
                    other.append(TABLE_ZH[t] + " " + "、".join(f"{w} {len(x)}" for w, x in zip(("新增", "删除", "修改"), d) if x))
        if other:
            sections.extend(["### 其他表", "", "；".join(other) + "。", ""])
    if dropped:
        table("丢掉的蓝图（材料或产品没有发布）", ["蓝图", "活动", "找不到的 typeID"],
              [(label(ty_new.get(b)) or b, ACT_ZH[a], ", ".join(map(str, m))) for b, a, m in dropped])
    lines.append("")
    lines.extend(sections)
    lines.append("插件数据由每周自动检查（.github/workflows/update-official.yml）生成，检查通过后直接提交到 main。")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="从 CCP 静态数据生成插件数据 official/data/")
    ap.add_argument("zip", nargs="?", help="下载好的 SDE 压缩包；不填就下载 CCP 最新的")
    ap.add_argument("--save-zip", metavar="PATH", help="下载的压缩包存到这里，不删（给 build_official.py 用）")
    ap.add_argument("--summary", help="有变化时把变化写成 Markdown 文件")
    ap.add_argument("--check", action="store_true", help="不联网，只校验仓库里已提交的文件")
    args = ap.parse_args()
    if args.check:
        sys.exit(check())
    if args.zip and args.save_zip:
        ap.error("--save-zip 只用来留下下载的压缩包，给了压缩包时不用写")

    if args.zip:
        new, dropped = build(args.zip)
    elif args.save_zip:
        download(latest_build(), args.save_zip)
        new, dropped = build(args.save_zip)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "sde.zip"
            download(latest_build(), zip_path)
            new, dropped = build(zip_path)

    old = {f: load(OUT / f) for f in TABLES}
    old = {f: d for f, d in old.items() if isinstance(d, dict)}
    old_manifest = load(OUT / "manifest.json")
    old_manifest = old_manifest if isinstance(old_manifest, dict) else {}
    def same(f):  # 内容没变，而且原来的 build 号不比这次的新（manifest 的 build 号不能比文件头部的旧）
        b = old[f].get("buildNumber") if f in old else None
        return isinstance(b, int) and b <= new[f]["buildNumber"] and stable(old[f]) == stable(new[f])

    changed = [f for f in TABLES if not same(f)]
    # 内容没变的文件保留原来的头部（generatedAt、build 号），格式不对时（例如换行符）按原来的头部重写
    docs = {f: new[f] if f in changed else {**new[f], **{k: old[f][k] for k in VOLATILE if k in old[f]}} for f in TABLES}
    texts = {f: dump(d).encode("utf-8") for f, d in docs.items()}
    errors = validate(new)
    for f, raw in texts.items():
        if len(raw) > MAX_BYTES:
            errors.append(f"{f}：{len(raw):,} 字节，超过 10 MB")
        if json.loads(raw) != docs[f]:
            errors.append(f"{f}：JSON 往返解析的结果和原来的不一样")
        for t in TABLES[f]:
            before, after = len((old.get(f) or {}).get(t) or []), len(new[f][t])
            if after < before * MIN_RATIO:
                errors.append(f"{f}：{t} 从 {before:,} 行变成 {after:,} 行，少了 20% 以上，SDE 可能有问题")
    if errors:
        for e in errors:
            print("错误：" + e)
        sys.exit("校验没通过，什么都没写")
    if dropped:
        msg = f"丢掉了 {len(dropped)} 行蓝图（材料或产品没有发布），见变化说明"
        print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else msg)

    head = new["types.json"]
    manifest = {"schema": SCHEMA, "dataRevision": DATA_REVISION, "buildNumber": head["buildNumber"],
                "sdeReleaseDate": head["sdeReleaseDate"], "generatedAt": head["generatedAt"],
                "files": {f: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "rows": len(new[f][MAIN_TABLE[f]])}
                          for f, raw in texts.items()}}
    if stable(old_manifest) == stable(manifest):  # 清单内容没变：保留原来的 generatedAt 和 build 号
        manifest.update((k, old_manifest[k]) for k in VOLATILE if k in old_manifest)
    texts["manifest.json"] = dump(manifest).encode("utf-8")
    write = [f for f, raw in texts.items() if not (OUT / f).exists() or (OUT / f).read_bytes() != raw]
    if not write:
        print(f"CCP 的 build {head['buildNumber']} 和仓库里的插件数据（build {old_manifest.get('buildNumber')}）内容完全一样，不用更新")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    for f in write:
        (OUT / f).write_bytes(texts[f])
    print(f"插件数据已更新到 build {manifest['buildNumber']}，改了：{', '.join(write)}")
    repaired = [f for f in write if f in TABLES and f not in changed]
    if repaired:
        print(f"  其中 {', '.join(repaired)} 内容没变，只是按生成脚本的格式重写（例如换行符）")
    for f in TABLES:
        print(f"  {f}：{len(texts[f]) / 1024 / 1024:.2f} MB，gzip {len(gzip.compress(texts[f], 9)) / 1024:.0f} KB；"
              + "，".join(f"{t} {len(new[f][t]):,}" for t in TABLES[f]))
    if args.summary:
        Path(args.summary).write_text(summary(old, new, old_manifest.get("buildNumber"), dropped), encoding="utf-8")

if __name__ == "__main__":
    main()
