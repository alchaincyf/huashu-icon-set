<sub><b>🌐 English</b> · <a href="README.md">中文</a></sub>

<div align="center">

# huashu-icon-set · End-to-End Icon Set Generation

**Generate a whole style-consistent icon set for a codebase: read the code, lock a style anchor, batch-generate, chroma-key, place, and report.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Doubao Only](https://img.shields.io/badge/Runtime-Doubao%20Only-orange)](https://www.doubao.com)
[![No API fees](https://img.shields.io/badge/API%20fees-Zero-green)](#dependencies)

</div>

---

## What it solves

Batch-generating icons for a codebase with AI image models hits three recurring problems:

**1. AI image models don't output real transparency.** Writing "transparent background" in the prompt does nothing — the output is RGB with no alpha channel. You have to generate a solid-color background and remove it in code.

**2. White-on-white can't be keyed out.** When the background color is too close to the icon's own colors, chroma keying can't tell background from icon — the result always has residue or over-deletion.

**3. Batch speed and per-icon precision pull in opposite directions.** Packing 16 icons into one grid image is fast but the grid may not align perfectly; generating icons one at a time is precise but slow at scale. This skill splits the tradeoff instead of picking a side: **batch grid generation is the default**, every cell gets self-checked after slicing, and only the cells that fail get regenerated individually — batch for throughput, single-icon generation as the precision fallback, not the default.

## Core workflow (Step 0–5)

| Step | What happens |
|---|---|
| 0 · Read manifest | Scan the codebase to locate icon asset directories, build a manifest (semantic name, usage site, target size), confirm with the user |
| 1 · Lock style anchor | Generate 3–4 style-direction candidates for one representative icon, verify chroma-key extraction works cleanly before scaling up |
| 2a · Batch grid (default) | 16 icons per group, one `image_gen` call produces a 4×4 grid image, `slice_grid.py` crops cells, hands off to Step 3 |
| 2b · Single-icon generation (precision fallback) | Cells that came out misaligned/wrong from the grid, or icons that inherently need high precision (symmetric icons, brand-color icons), get regenerated individually via `image_edit` |
| 3 · Chroma-key extraction | `chroma_key.py` does color keying + edge despill + trim + centering, self-checks each output as `OK` / `BG` / `SMALL` / `EMPTY` |
| 4 · Placement | Places PNGs at manifest paths; for Xcode projects, auto-creates `.imageset` + `Contents.json` and updates code references; runs a build check if the project is compilable |
| 5 · Delivery report | Honest report: how many icons, which went through the grid path vs. the fallback path, which failed self-check, which code files changed |

## 🔴 Hard-won lessons

Every rule here comes from a real failure, not theory:

| Lesson | What went wrong |
|---|---|
| AI image models don't output real transparency | "Transparent background" in the prompt does nothing — must generate a solid background and key it out in code |
| White/light background + white/light icon base | Chroma keying always leaves residue — background color must strongly contrast the icon's own colors |
| Icon elements share the background color | On a green background, models often paint checkmarks/arrows/magnifying glasses green too, and they get keyed out along with the background |
| Brand-color icons on a same-color background | A green WeChat icon can't sit on a green background — needs a contrasting background like blue |
| Abstract geometric descriptions vs. concrete nouns | "A rectangle with L-shaped marks at each corner" confuses the model; "scissors" nails it immediately |
| Grid-batch alignment risk | AI doesn't guarantee perfect grid alignment — solved by Step 3 self-check + Step 2b fallback regeneration, not by banning batch generation outright |

## Quick start

In a Doubao Work Tasks session (with "Local Computer" enabled):

```
Use huashu-icon-set to generate an icon set for this project
```

The skill handles everything itself — reading the codebase, building the manifest, locking a style anchor, batch-generating, chroma-keying, placing files, and reporting. To run a step manually:

```bash
# Step 2a batch grid: crop a 4x4 grid image into 16 raw cells (crop only, no keying)
python3 <skill_dir>/scripts/slice_grid.py grid.png --rows 4 --cols 4 \
  --names icon1,icon2,...,icon16 --outdir ./raw --no-trim --cell-size 0

# Step 3 chroma-key extraction (same script for both grid-cropped and individually generated icons)
python3 <skill_dir>/scripts/chroma_key.py ./raw ./output --size 512 --padding 0.12
```

## Dependencies

- Doubao's built-in image generation (`image_gen` / `image_edit` with the `image_reference_url_list` reference-image mechanism) — **this skill does not work outside a Doubao image-gen environment**, that's a hard constraint, not optional
- Python 3 + Pillow + numpy (`pip install Pillow numpy`)

## A real-world delivery

This workflow was validated in 2026-08: generating 44 icons for a macOS screen-recording app — camera, mic, record region, export-to-Bilibili/Xiaohongshu/WeChat, etc. — each named by purpose (`camera.png`, `export-bilibili.png`), zero placeholder names like `icon1.png`. Along the way it hit two real problems (white-on-white keying failure, brand-color icons colliding with the background) — both solutions are written into `SKILL.md`. Full writeup on the WeChat account "AI进化论-花生".

## Layout

```
SKILL.md                     Agent entry point: full Step 0–5 workflow + hard-won lessons
scripts/
  chroma_key.py               Main extraction script: color keying + despill + trim + center + self-check
  slice_grid.py                Grid-slicing script: used by Step 2a's default path, crops only, no keying
references/
  prompt-guide.md              Prompt methodology: style reference table, grid-batch + single-icon templates, background-color strategy, checklist
```

## License

MIT — free for personal and commercial use, no authorization required.

## Author

[花叔 (Huashu) · @AlchainHust](https://x.com/AlchainHust) — AI Native Coder, indie developer, AI content creator.

---

<div align="center">

MIT License · Follow the WeChat account "花叔" for more AI practice

</div>
