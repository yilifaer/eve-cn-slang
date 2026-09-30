# EVE Online 中文黑话表（欧服）

[![check](https://github.com/yilifaer/eve-cn-slang/actions/workflows/check.yml/badge.svg)](https://github.com/yilifaer/eve-cn-slang/actions/workflows/check.yml)

欧服（Tranquility）中文玩家实际使用的 EVE 黑话、缩写、舰队用语的中英对照表，附带 CCP 官方中英名称表。最初是为 QQ 群和 Discord 之间的自动翻译整理的，所有词条都用真实的舰队 ping 和群聊记录测试过。

> English summary at the bottom.

## 数据一览

| 部分 | 数量 | 说明 | 许可 |
|---|---|---|---|
| [`glossary.yaml`](glossary.yaml) 人工整理的黑话表 | **305 条**，另有 859 个别名 | 舰队行动、船型俗称、装备、建筑与主权、虫洞、工业与市场、PvE、聊天缩写、国服叫法 | CC BY 4.0 |
| [`official/`](official/) 官方中英名称表 | **12,396 条** | 从 CCP 静态数据生成（build 3552227）：舰船、装备等物品 9,296，分组 709，大类 27，星系 1,974，星座 323，星域 67 | CCP 版权，仅限非商业用途，见 [NOTICE](official/NOTICE.md) |

黑话表按类别：舰队 71、聊天 60、装备 34、工业 32、建筑 30、船型 27、虫洞 23、PvE 16、安全等级与区域 12。

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

## 用在 koishi-plugin-dcqq-bridge 里

在插件配置的「术语表」里：打开 `eve`（插件自带官方名称表），`slangFile` 填本仓库 `glossary.yaml` 的本地路径。更新文件后发 `bridge.reload` 生效。

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

更新官方名称表：`python scripts/build_official.py`（从 koishi-plugin-dcqq-bridge 下载最新生成的数据）。

## 许可证

- `glossary.yaml`、脚本和文档：[CC BY 4.0](LICENSE)。使用时请注明来源：「EVE Online 中文黑话表（github.com/yilifaer/eve-cn-slang）」。
- `official/` 目录：**不适用 CC BY 4.0**，版权归 CCP hf.，按 EVE 开发者许可协议仅限非商业、非营利用途，详见 [official/NOTICE.md](official/NOTICE.md)。

© 2014 CCP hf. All rights reserved. "EVE", "EVE Online", "CCP", and all related logos and images are trademarks or registered trademarks of CCP hf.

---

## English

A glossary of EVE Online slang, abbreviations and fleet jargon as actually used by **Chinese players on Tranquility**, with the English terms they correspond to. It was built for machine translation between Chinese QQ groups and English Discord channels, and every entry was tested against real fleet pings and chat logs.

- [`glossary.yaml`](glossary.yaml): **305 hand-curated entries** (859 aliases), licensed **CC BY 4.0**. Each entry has `en`, `zh`, `mode` (`keep` / `force` / `hint`) and `dir` (`both` / `en2zh` / `zh2en`); see the format section above.
- [`official/`](official/): **12,396 official English/Chinese names** (types, groups, categories, systems, constellations, regions) generated from CCP's Static Data Export. **Not** covered by CC BY 4.0: © CCP hf., non-commercial use only under the EVE Developer License Agreement; see [official/NOTICE.md](official/NOTICE.md).

Contributions are welcome via issues and pull requests. Please run `python scripts/check.py` before submitting.
