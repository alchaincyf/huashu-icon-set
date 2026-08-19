<sub>🌐 <a href="README.en.md">English</a> · <b>中文</b></sub>

<div align="center">

# huashu-icon-set · 成套图标生成

**为一个项目端到端生成一整套风格统一的图标：读代码定清单 → 定风格锚点 → 批量生图 → 智能抠图 → 落位 → 交付报告。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Doubao Only](https://img.shields.io/badge/Runtime-Doubao%20Only-orange)](https://www.doubao.com)
[![No API fees](https://img.shields.io/badge/API%20fees-Zero-green)](#依赖)

</div>

---

## 它解决什么

给一个项目批量配图标，AI 生图这条路上有三个反复出现的坑：

**1. AI 不输出真透明背景。** prompt 里写"透明背景"没用，出来的是 RGB 无 alpha，必须生成纯色背景再用代码抠。

**2. 白底白底座抠不干净。** 背景色和图标主体颜色太接近，颜色键控分不出哪是背景哪是图标，抠出来必然残留或误删。

**3. 批量生成的效率和精度是一对矛盾。** 16 个图标拼一张网格图一次出，快，但网格可能对不齐；一个个单独生成，准，但 16 次调用摊下来很慢。这个 skill 把矛盾拆开处理：**默认走网格批量**，切完自检，不达标的那一格再单独逐个重生——不是二选一，是批量打底、精度兜底。

## 核心流程（Step 0–5）

| Step | 做什么 |
|---|---|
| 0 · 读清单 | 扫代码定位图标资源目录，梳理语义名称、使用位置、目标尺寸，列清单给用户确认 |
| 1 · 定风格锚点 | 先出 3–4 个风格方向的单图标候选，用户选定后过一次抠图验证，确认背景能干净移除再往下走 |
| 2a · 网格批量（默认） | 16 个图标一组，一次 `image_gen` 出一张 4×4 网格图，`slice_grid.py` 切格，交给 Step 3 抠图 |
| 2b · 逐个生成（精度兜底） | 网格里对不齐/画错的那几个，或本来就要求高精度的（对称图标、品牌色图标），单独 `image_edit` 重生 |
| 3 · 智能抠图 | `chroma_key.py` 做颜色键控 + despill + trim + 居中，逐张自检状态：`OK` / `BG` / `SMALL` / `EMPTY` |
| 4 · 落位 | 按清单放入项目路径，Xcode 项目自动建 `.imageset` + `Contents.json`，更新代码引用，能编译的项目跑一次构建验证 |
| 5 · 交付报告 | 如实汇报生成了几个、哪些走网格哪些走兜底、哪些没达标、代码引用改了哪些文件 |

## 🔴 血泪教训

这些规则全部来自真实踩坑，不是理论推导：

| 教训 | 后果 |
|---|---|
| AI 生图不输出真透明背景 | prompt 写"透明背景"没用，必须纯色背景 + 代码抠 |
| 白色/浅色背景 + 白色/浅色底座 | 抠图必残，背景色必须与图标主体高对比 |
| 图标元素颜色 = 背景色 | 绿色背景时模型常把对勾/箭头/放大镜也画成绿色，元素被一起抠掉 |
| 品牌色图标用同色背景 | 微信绿图标不能用绿底，必须换蓝底等对比色 |
| 抽象几何描述 vs 具象名词 | 写"矩形四个角各有L形短线"模型理解差，写"剪刀"立刻准 |
| 网格批量对齐风险 | AI 不保证网格严格对齐，靠 Step 3 自检 + Step 2b 兜底重生解决，不是靠禁止批量 |

## 快速上手

在豆包工作任务模式（开「本地电脑」）里：

```
用 huashu-icon-set 给这个项目配一套图标
```

它会自己去读项目代码梳理清单、定风格锚点、批量生图、抠图、落位、交付报告——不需要你手动跑下面的命令，但如果要单独执行某一步：

```bash
# Step 2a 网格批量：切一张 4×4 网格图（只裁不抠）
python3 <skill目录>/scripts/slice_grid.py 网格图.png --rows 4 --cols 4 \
  --names icon1,icon2,...,icon16 --outdir ./raw --no-trim --cell-size 0

# Step 3 智能抠图（网格切出来的、单独生成的都吃这一个脚本）
python3 <skill目录>/scripts/chroma_key.py ./raw ./output --size 512 --padding 0.12
```

## 依赖

- 豆包内置生图能力（`image_gen` / `image_edit` 的 `image_reference_url_list` 参考图机制）——**离开豆包生图环境跑不通**，这是本 skill 的硬约束，不是可选项
- Python 3 + Pillow + numpy（`pip install Pillow numpy`）

## 一次真实交付

这套流程在 2026-08 实测跑通：给一个 macOS 录屏 app（花录）配了 44 个图标——摄像头、麦克风、录制区域、导出到 B站/小红书/微信等，全部按用途命名（`camera.png`、`export-bilibili.png`），零 `icon1.png` 这种占位名。过程中撞上白底白座抠不干净、品牌色图标撞背景色两个坑，都在这份 SKILL.md 里写了解法。完整过程见公众号「AI进化论-花生」。

## 目录

```
SKILL.md                     agent 入口：Step 0–5 完整流程 + 血泪教训
scripts/
  chroma_key.py               主力抠图脚本：颜色键控 + despill + trim + 居中 + 自检
  slice_grid.py                网格切图脚本：Step 2a 默认路径用，只裁格子不抠图
references/
  prompt-guide.md              生图 prompt 方法论：风格参考名表、网格批量+单图标模板、背景色策略、检查清单
```

## 许可证

MIT —— 个人和商业使用都免费，无需授权。

## 作者

[花叔 · @AlchainHust](https://x.com/AlchainHust) —— AI Native Coder，独立开发者，AI 自媒体博主。

---

<div align="center">

MIT License · 关注公众号「花叔」获取更多 AI 实践

</div>
