"""检查 glossary.yaml：格式错误会让检查失败；可能误伤普通句子的写法给出警告。

用法：python scripts/check.py [glossary.yaml]
需要：pip install pyyaml
"""
import re, sys, urllib.request
from collections import defaultdict
import yaml

FILE = sys.argv[1] if len(sys.argv) > 1 else "glossary.yaml"
MODES = {"keep", "force", "hint"}
DIRS = {"both", "en2zh", "zh2en"}
CATS = {"fleet", "ship", "module", "structure", "wormhole", "industry", "space", "pve", "chat"}
KEYS = {"en", "zh", "mode", "dir", "en_aliases", "zh_aliases", "category", "note", "confidence"}
WORDS_URL = "https://raw.githubusercontent.com/yilifaer/koishi-plugin-dcqq-bridge/main/data/common-words.txt"
CJK = re.compile(r"[\u4e00-\u9fff]")


def common_words():
    try:
        with urllib.request.urlopen(WORDS_URL, timeout=30) as r:
            return {w.strip().lower() for w in r.read().decode("utf-8").splitlines() if w.strip() and not w.startswith("#")}
    except Exception as e:  # 离线时只跳过常用词检查
        print(f"（没能下载常用词表，跳过常用词检查：{e}）")
        return set()


def main():
    data = yaml.safe_load(open(FILE, encoding="utf-8"))
    errors, warns = [], []
    common = common_words()
    seen = defaultdict(list)
    if not isinstance(data, list):
        print("错误：文件最外层必须是列表"); sys.exit(1)
    for i, e in enumerate(data, 1):
        tag = f"第 {i} 条（{e.get('en') if isinstance(e, dict) else e!r}）"
        if not isinstance(e, dict):
            errors.append(f"{tag}：不是对象"); continue
        for k in ("en", "zh", "mode", "dir"):
            if not isinstance(e.get(k), str) or not e[k].strip():
                errors.append(f"{tag}：缺少 {k}")
        if e.get("mode") not in MODES: errors.append(f"{tag}：mode 只能是 keep / force / hint")
        if e.get("dir") not in DIRS: errors.append(f"{tag}：dir 只能是 both / en2zh / zh2en")
        if "category" in e and e["category"] not in CATS: warns.append(f"{tag}：category「{e['category']}」不在常用分类里")
        extra = set(e) - KEYS
        if extra: errors.append(f"{tag}：不认识的字段 {sorted(extra)}")
        mode, d = e.get("mode"), e.get("dir")
        ens = [e.get("en")] + list(e.get("en_aliases") or [])
        zhs = [e.get("zh")] + list(e.get("zh_aliases") or [])
        for a in ens:
            if not isinstance(a, str): errors.append(f"{tag}：英文别名必须是文字"); continue
            if len(a.strip()) < 2: errors.append(f"{tag}：英文「{a}」少于 2 个字符")
            if d in ("both", "en2zh"): seen[("en", a.lower())].append(i)
            if re.fullmatch(r"[a-z]{1,3}", a) and a in common and d in ("both", "en2zh"):
                warns.append(f"{tag}：小写的「{a}」是普通英文单词，会命中普通句子")
            if mode in ("force", "keep") and d in ("both", "en2zh") and " " not in a and a.lower() in common and len(a) > 3:
                warns.append(f"{tag}：「{a}」是常用英语单词，用 {mode} 会误伤普通句子，考虑改成 hint 或更长的短语")
        for a in zhs:
            if not isinstance(a, str): errors.append(f"{tag}：中文别名必须是文字"); continue
            if len(a.strip()) < 2: errors.append(f"{tag}：中文「{a}」少于 2 个字")
            if d in ("both", "zh2en"): seen[("zh", a)].append(i)
            if mode == "force" and d in ("both", "zh2en") and len(CJK.findall(a)) == len(a) == 2:
                warns.append(f"{tag}：2 个字的「{a}」用于中译英强制替换，中文匹配不看词边界，可能误伤普通句子")
    for (lang, s), idx in seen.items():
        if len(set(idx)) > 1:
            warns.append(f"「{s}」同时出现在第 {sorted(set(idx))} 条（{'英译中' if lang == 'en' else '中译英'}），以最长、最先出现的为准")
    for w in warns: print("警告：" + w)
    for x in errors: print("错误：" + x)
    print(f"共 {len(data)} 条：{len(errors)} 个错误，{len(warns)} 个警告")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
