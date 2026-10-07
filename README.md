# EVE Online 中文黑话表（欧服）

[![check](https://github.com/yilifaer/eve-cn-slang/actions/workflows/check.yml/badge.svg)](https://github.com/yilifaer/eve-cn-slang/actions/workflows/check.yml)

欧服（Tranquility）中文玩家实际使用的 EVE 黑话、缩写、舰队用语的中英对照表，附带 CCP 官方中英名称表。最初是为 QQ 群和 Discord 之间的自动翻译整理的，所有词条都用真实的舰队 ping 和群聊记录测试过。

> English summary at the bottom.

## 数据一览

| 部分 | 数量 | 说明 | 许可 |
|---|---|---|---|
| [`glossary.yaml`](glossary.yaml) 人工整理的黑话表 | **325 条**，另有 907 个别名 | 舰队行动、船型俗称、装备、建筑与主权、虫洞、工业与市场、PvE、聊天缩写、国服叫法 | CC BY 4.0 |
| [`official/`](official/) 官方中英名称表 | **12,396 条** | 从 CCP 静态数据生成（build 3579973）：舰船、装备等物品 9,296，分组 709，大类 27，星系 1,974，星座 323，星域 67 | CCP 版权，仅限非商业用途，见 [NOTICE](official/NOTICE.md) |
| [`official/data/`](official/data/) 插件数据 | 见 [`manifest.json`](official/data/manifest.json) | 从 CCP 静态数据生成：物品（含拼音）、工业、星图，给 QQ 机器人插件在线读取，格式见下面的「插件数据」 | 同上 |

黑话表按类别：舰队 87、聊天 61、装备 34、工业 32、建筑 30、船型 27、虫洞 24、PvE 16、安全等级与区域 14。

官方表可以直接在 GitHub 上搜索：打开 [`official/eve-official.csv`](official/eve-official.csv)，GitHub 会显示成可搜索的表格。

## 黑话表格式

每一条是一个 YAML 对象：

```yaml
- en: "cap save"
  zh: "旗舰救援"
  mode: force
  dir: en2zh
  en_aliases: ["capsave", "cap-save"]
  category: fleet
  note: "救被抓住的旗舰"
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `en` | 是 | 英文玩家的写法 |
| `zh` | 是 | 欧服中文玩家的叫法 |
| `mode` | 是 | `keep`：原样保留不翻译（如 CTA、FC）；`force`：一定换成对应的词；`hint`：只作参考，交给翻译模型按上下文判断 |
| `dir` | 是 | `both` / `en2zh`（只用于英译中）/ `zh2en`（只用于中译英） |
| `en_aliases`、`zh_aliases` | 否 | 其他写法，匹配到时输出标准写法。国服叫法放在 `zh_aliases` 里 |
| `category` | 否 | fleet / ship / module / structure / wormhole / industry / space / pve / chat |
| `note` | 否 | 给人看的简短解释 |

**匹配规则**（[koishi-plugin-dcqq-bridge](https://github.com/yilifaer/koishi-plugin-dcqq-bridge) 的实现，别的工具可以参考）：

- 最长的优先；
- 英文要求前后是词边界，不区分大小写，允许末尾多一个 `s`；
- **3 个字母以内的英文只匹配大小写完全一致的写法**（FC 不会命中 fc 以外的写法，`me` 这种普通单词不会被当成 ME）；
- 中文匹配不看词边界，所以 2 个字的中文用 `force` 要谨慎（「高安」会命中「提高安全」）。

## 官方表格式

[`official/eve-official.json`](official/eve-official.json) 的 `entries` 里每一条：

| 字段 | 说明 |
|---|---|
| `kind` | `category` 大类 / `group` 分组 / `type` 物品 / `region` 星域 / `constellation` 星座 / `system` 星系 |
| `en`、`zh` | 官方英文名、中文名 |
| `cat` | 类别标记，**只有舰船（`ship`）和建筑（`structure`）物品才有**，其他条目没有这个字段。插件用它给以「级」结尾的船名加一个去掉「级」的写法，以及识别建筑通知里的建筑类型 |

```json
{"kind": "type", "en": "Armageddon", "zh": "末日沙场级", "cat": "ship"}
```

[`official/eve-official.csv`](official/eve-official.csv) 是同样的四列（`kind,en,zh,cat`），没有 `cat` 时留空。

## 插件数据（official/data/）

给 QQ 机器人插件 koishi-plugin-eve-market（查价、批量估价、工业计算）在线读取的数据，由 [`scripts/build_data.py`](scripts/build_data.py) 从 CCP 静态数据生成。GitHub 上每周三自动检查一次，有变化并且检查通过后**直接提交到 `main`**（不开合并请求）。物品数、build 号这些会变的数字都写在 `manifest.json` 里。

| 文件 | 内容 |
|---|---|
| [`manifest.json`](official/data/manifest.json) | 很小，插件只轮询这个文件：`schema`、`dataRevision`、`buildNumber`、`sdeReleaseDate`、`generatedAt`，以及每个数据文件的 `sha256`、`bytes`（字节数）、`rows`（`types`、`blueprints`、`systems` 的行数） |
| [`types.json`](official/data/types.json) | 所有已发布的物品（含拼音），以及分组、大类、市场分组、元分组 |
| [`industry.json`](official/data/industry.json) | 蓝图（制造、反应、发明）、Upwell 建筑的工业加成、工业改装件、改装件的目标过滤器 |
| [`universe.json`](official/data/universe.json) | 星域、星座、星系（含虫洞空间）、NPC 空间站、势力、星门连接 |

网址：先读 manifest，有变化时把三个数据文件一起下载，逐个核对 `sha256`。数据文件和 manifest 在同一个目录。

- `https://raw.githubusercontent.com/yilifaer/eve-cn-slang/main/official/data/manifest.json`
- 备用（jsDelivr，有缓存，更新最多可能晚约 12 小时）：`https://cdn.jsdelivr.net/gh/yilifaer/eve-cn-slang@main/official/data/manifest.json`

**格式**：

- 每个数据文件开头是头部键：`schema`、`buildNumber`、`sdeReleaseDate`、`source`、`license`、`generatedAt`。内容没变的文件不重写，所以各文件头部的 build 号可能比 manifest 旧，**以 manifest 为准**；manifest 的 `generatedAt` 是数据内容上次变化的时间，不是上次检查的时间（SDE 没有变化时它不会更新）。
- 大部分表带一个列名数组（`columns`、`groupColumns`……），行是紧凑的 JSON 数组；`industry.json` 的 `structures`、`rigs`、`filters` 是对象数组，一行一个对象。都是一行一条、按 id 排序。**请按列名（字段名）取值**：以后可能加列、加表（这时 `dataRevision` 加 1）；只有改列名、改含义这种不兼容的变化才会把 `schema` 加 1。
- 整数写整数，其他数字保留 6 位小数；没有中文名、或者中文和英文一样时 `zh` 是 `""`；代号星系（例如 `YM-SRU`）、代号星座和星域的 `zh` 也是 `""`。

```json
"columns": ["id","en","zh","group","marketGroup","metaGroup","techLevel","volume","packagedVolume","portionSize","variationParent","capacity","py"],
"types": [
[638,"Raven","乌鸦级",27,80,1,1,470000,50000,1,null,830,"wuyaji wyj"],
```

| 表 | 列 / 字段 | 说明 |
|---|---|---|
| `types` | `id`、`en`、`zh`、`group` | typeID、英文名、中文名、分组 |
| | `marketGroup` | 市场分组；不是 `null` 才能在市场上交易 |
| | `metaGroup`、`techLevel` | 元分组（一级科技、二级科技、势力……）、科技等级 |
| | `volume`、`packagedVolume` | 体积（m³）；打包体积和体积一样时 `packagedVolume` 是 `null`，算运费用 `packagedVolume ?? volume` |
| | `portionSize` | 一份的数量（矿石精炼等按份计算） |
| | `variationParent` | 势力型、海军型等变体对应的基础型号 |
| | `capacity` | 容量，只给容量大于 0 的物品写（装配估价算装填弹药用） |
| | `py` | 拼音，只给能上市场、有中文名的物品写：「全拼 首字母」，空格隔开，小写、不带声调，名字里的拉丁字母和数字原样保留，例如 `巡航导弹发射器 II` → `"xunhangdaodanfasheqiii xhddfsqii"`；多音字最多 4 种读法组合，每种都是一对「全拼 首字母」（第 1、3……个是全拼，第 2、4……个是首字母，首字母一样也照写），例如 `长肢龙鹿的卵` → `"changzhilongludeluan czlldl zhangzhilongludeluan zzlldl changzhilongludiluan czlldl zhangzhilongludiluan zzlldl"` |
| `groups` | `id`、`category`、`en`、`zh`、`published` | 分组（`published` 是 true / false） |
| `categories` | `id`、`en`、`zh`、`published` | 大类 |
| `marketGroups` | `id`、`parent`、`en`、`zh` | 市场分组（`parent` 是上级） |
| `metaGroups` | `id`、`en`、`zh` | 元分组 |
| `blueprints` | `blueprint`、`activity`、`time`、`maxRuns`、`products`、`materials` | `activity`：`m` 制造、`r` 反应、`i` 发明；`time` 是秒；`maxRuns` 是 SDE 的 `maxProductionLimit`；`products` 是 `[typeID, 数量]`，发明多一个成功率；`materials` 是 `[typeID, 数量]` |
| `structures` | `id`、`en`、`zh`、`group`、`rigSize`、`highsec`、`bonus` | Upwell 工程复合体、精炼厂、堡垒。`rigSize` 是能装的改装件尺寸：2 = M、3 = L、4 = XL；`bonus` 按活动（`m`、`r`、`i`、`c` 拷贝、`rm` 材料研究、`rt` 时间研究）给 `me`、`te`、`cost` 的乘数（例如 0.99）；没有工业加成的建筑是 `{}`；`highsec` 是 false 时不能放在高安 |
| `rigs` | `id`、`en`、`zh`、`group`、`size`、`sec`、`effects` | 工业改装件。`size` 和建筑的 `rigSize` 一样才能装（2 = M、3 = L、4 = XL）；`sec` 是高安 `h`、低安 `l`、00 `n` 的倍数，`null` 表示这里不生效；`effects` 每一条是 `[活动, me/te/cost, 过滤器 id, 百分比]`：产品命中过滤器时按这个百分比加成（例如 `-2` 再乘 `sec` 里的倍数），过滤器是 `null` 时对这个活动的所有产品生效。同一个改装件对不同产品的百分比可能不一样（Thukker 改装件对旗舰组件、高级旗舰组件的材料加成是 -3.7，来自属性 2653；对其他产品是 -2），所以要用每一条自己的百分比 |
| `filters` | `id`、`name`、`categories`、`groups` | 改装件的目标过滤器：产品的大类在 `categories` 里、或者分组在 `groups` 里就算命中 |
| `regions` | `id`、`en`、`zh` | 星域 |
| `constellations` | `id`、`region`、`en`、`zh` | 星座 |
| `systems` | `id`、`constellation`、`region`、`security`、`en`、`zh` | 星系（含虫洞空间）；`security` 是安全等级 |
| `stations` | `id`、`system` | NPC 空间站所在的星系（SDE 里没有空间站名字） |
| `factions` | `id`、`en`、`zh` | 势力 |
| `jumps` | `a`、`b` | 星门连接，不分方向，`a < b` |

**没有收录**：蓝图的拷贝和研究；Upwell 前哨改装件（用的是另一套属性）；交易中心（由插件自己配置）。

**自己生成**：`pip install pypinyin==0.55.0 && python scripts/build_data.py`（下载 CCP 最新的静态数据，内容没变时不改文件；拼音库的版本要和 `build_data.py`、`update-official.yml` 里的一致，不然拼音列会变）；`python scripts/build_data.py --check` 不联网校验仓库里的文件。

**许可**：和官方名称表一样，版权归 CCP hf.，按 EVE 开发者许可协议仅限非商业用途，见 [official/NOTICE.md](official/NOTICE.md)。

## 用在 koishi-plugin-dcqq-bridge 里

**推荐在线读取（插件 0.4.0 起）**：插件 0.4.0 起可以直接填本仓库文件的网址，插件每 6 小时自动更新。本仓库更新词条或官方名称后，不用等插件发新版本。

- 黑话表：`https://raw.githubusercontent.com/yilifaer/eve-cn-slang/main/glossary.yaml`
- 官方名称表：`https://raw.githubusercontent.com/yilifaer/eve-cn-slang/main/official/eve-official.json`

**也可以用本地文件**：在插件配置的「术语表」里，打开 `eve`（插件自带官方名称表），`slangFile` 填本仓库 `glossary.yaml` 的本地路径。更新文件后发 `bridge.reload` 生效。

自己联盟或军团专用的叫法，可以另外写一个同样格式的文件，两个路径用 `;;` 连起来（插件 0.3.1 起支持），后面文件里同一个原文的词条覆盖前面的：

```
data/eve-cn-slang/glossary.yaml;;data/dcqq-bridge/local-slang.yaml
```

## 参与贡献

欢迎提 Issue 或 Pull Request，补充词条或者纠正错误。

- 写**欧服中文玩家实际说的**叫法，不确定就在 Issue 里讨论；
- 确定、不会有歧义的用 `force`；普通英文单词（keep、point、web、blob……）只能用 `hint`，或者写成更长的短语（例如 `cap save` 而不是 `cap`）；
- 不收录玩家、军团、联盟的名字，也不收录政治相关内容；
- 提交前运行一次检查：`pip install pyyaml && python scripts/check.py`。有错误时 GitHub 上的自动检查会失败；警告只是提醒，按需处理。

更新官方名称表：`python scripts/build_official.py`（直接从 CCP 下载最新的静态数据，名称和类别标记都没有变化时不改文件）。GitHub 上每周三也会自动检查一次，有变化会自动开一个合并请求。

## 许可证

- `glossary.yaml`、脚本和文档：[CC BY 4.0](LICENSE)。使用时请注明来源：「EVE Online 中文黑话表（github.com/yilifaer/eve-cn-slang）」。
- `official/` 目录：**不适用 CC BY 4.0**，版权归 CCP hf.，按 EVE 开发者许可协议仅限非商业、非营利用途，详见 [official/NOTICE.md](official/NOTICE.md)。

© 2014 CCP hf. All rights reserved. "EVE", "EVE Online", "CCP", and all related logos and images are trademarks or registered trademarks of CCP hf.

---

## English

A glossary of EVE Online slang, abbreviations and fleet jargon as actually used by **Chinese players on Tranquility**, with the English terms they correspond to. It was built for machine translation between Chinese QQ groups and English Discord channels, and every entry was tested against real fleet pings and chat logs.

- [`glossary.yaml`](glossary.yaml): **325 hand-curated entries** (907 aliases), licensed **CC BY 4.0**. Each entry has `en`, `zh`, `mode` (`keep` / `force` / `hint`) and `dir` (`both` / `en2zh` / `zh2en`); see the format section above.
- [`official/`](official/): **12,396 official English/Chinese names** (types, groups, categories, systems, constellations, regions) generated from CCP's Static Data Export. Each entry has `kind`, `en` and `zh`; ship and structure types also carry `cat` (`ship` / `structure`). **Not** covered by CC BY 4.0: © CCP hf., non-commercial use only under the EVE Developer License Agreement; see [official/NOTICE.md](official/NOTICE.md).
- [`official/data/`](official/data/): data for the koishi-plugin-eve-market QQ bot plugin, generated from the Static Data Export by `scripts/build_data.py`: `types.json` (all published types with Chinese names and pinyin, plus groups, categories, market groups and meta groups), `industry.json` (manufacturing / reaction / invention blueprints, Upwell structure bonuses, industry rigs and their target filters) and `universe.json` (regions, constellations, systems, NPC stations, factions, stargate jumps). Poll `manifest.json` (build number, `sha256`, size and row count of each file). Most tables are a column-name array plus compact rows; `structures`, `rigs` and `filters` in `industry.json` are one JSON object per line. Rows are sorted by id; read columns by name, as columns may be added (`schema` only changes on incompatible changes). Unchanged files are not rewritten, so trust the build number in `manifest.json`, not the file headers. Checked weekly; when the data changes it is validated and committed to `main` automatically. Same CCP license as `official/`; see [official/NOTICE.md](official/NOTICE.md).

Contributions are welcome via issues and pull requests. Please run `python scripts/check.py` before submitting.
