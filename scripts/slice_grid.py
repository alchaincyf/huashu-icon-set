#!/usr/bin/env python3
"""
slice_grid.py — 把网格排列的图标大图切成独立透明 PNG，并逐张自检。

用法:
    python3 slice_grid.py SHEET --rows R --cols C \
        --names security,favorites,settings,... \
        --outdir ./icons \
        [--cell-size 512] [--padding 0.12] [--gap 0] \
        [--remove-bg] [--bg-tolerance 32] [--no-trim]

名称按行优先顺序（从左到右、从上到下）分配。
--names 也可用 --names-file 传入（txt 每行一个，或 json 数组）。

自检状态:
    OK     正常
    EMPTY  单元格全透明（无内容）
    SMALL  内容占比过小（可能裁切不全）
    BG     边角残留非透明背景
"""

import argparse
import json
import sys
from collections import Counter, deque
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("缺少 Pillow，请先安装: pip install Pillow")


# ---------- 名称解析 ----------

def parse_names(args):
    if args.names_file:
        text = Path(args.names_file).read_text(encoding="utf-8")
        if args.names_file.lower().endswith(".json"):
            data = json.loads(text)
            if isinstance(data, dict):
                return [data[k] for k in sorted(data.keys(), key=_sort_key)]
            return [str(x) for x in data]
        return [line.strip() for line in text.splitlines() if line.strip()]
    if args.names:
        return [n.strip() for n in args.names.split(",") if n.strip()]
    return None


def _sort_key(k):
    """支持 '0,1' / 'r0c1' / '0' 等键的排序。"""
    import re
    nums = re.findall(r"\d+", str(k))
    return tuple(int(n) for n in nums) if nums else (str(k),)


# ---------- 背景移除 ----------

def _color_dist(c1, c2):
    return max(abs(int(c1[i]) - int(c2[i])) for i in range(3))


def remove_background(img, tolerance=32):
    """从四边/四角洪水填充，移除连通的纯色背景，转为透明。

    优先用 numpy 加速；不可用时退化为纯 Python BFS。
    """
    img = img.convert("RGBA")
    w, h = img.size

    # 四角已透明则无需处理
    corners = [img.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    if all(c[3] < 16 for c in corners):
        return img

    bg_color = Counter(corners).most_common(1)[0][0]

    try:
        import numpy as np
        from scipy import ndimage
        return _remove_bg_numpy(img, bg_color, tolerance, ndimage)
    except ImportError:
        return _remove_bg_py(img, bg_color, tolerance)


def _remove_bg_numpy(img, bg_color, tolerance, ndimage):
    import numpy as np

    arr = np.array(img)
    rgb = arr[:, :, :3].astype(int)
    dist = np.max(np.abs(rgb - np.array(bg_color[:3], dtype=int)), axis=2)
    match = dist <= tolerance

    # 只保留从边缘连通的区域作为背景
    structure = np.ones((3, 3), dtype=int)
    labeled, n = ndimage.label(match, structure=structure)

    edge_labels = set()
    edge_labels.update(labeled[0, :].tolist())
    edge_labels.update(labeled[-1, :].tolist())
    edge_labels.update(labeled[:, 0].tolist())
    edge_labels.update(labeled[:, -1].tolist())
    edge_labels.discard(0)

    bg_mask = np.isin(labeled, list(edge_labels)) if edge_labels else np.zeros_like(match)
    arr[bg_mask, 3] = 0
    return Image.fromarray(arr, "RGBA")


def _remove_bg_py(img, bg_color, tolerance):
    w, h = img.size
    px = img.load()
    visited = bytearray(w * h)
    q = deque()

    def seed(x, y):
        i = y * w + x
        if not visited[i] and _color_dist(px[x, y], bg_color) <= tolerance:
            visited[i] = 1
            q.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    while q:
        x, y = q.popleft()
        px[x, y] = (0, 0, 0, 0)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                i = ny * w + nx
                if not visited[i] and _color_dist(px[nx, ny], bg_color) <= tolerance:
                    visited[i] = 1
                    q.append((nx, ny))
    return img


# ---------- 自检 ----------

def self_check(img, raw_w, raw_h):
    """在裁切（trim）后、放画布前检测。

    返回 (status, detail)。status: OK / EMPTY / SMALL / BG。
    raw_w/raw_h 是从大图切出的原始单元格尺寸（扣除 gap 后），用于 SMALL 判断。
    """
    bbox = img.getbbox()
    if bbox is None:
        return "EMPTY", "全透明，无内容"

    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    raw_area = max(raw_w * raw_h, 1)
    ratio = (bw * bh) / raw_area
    if ratio < 0.10:
        return "SMALL", f"内容仅占原始单元格 {ratio:.0%}，可能裁切不全"

    # 残留背景：检测四条边是否被近乎均匀的纯色不透明像素铺满
    w, h = img.size
    px = img.load()
    step = max(1, min(w, h) // 24)
    edge_pixels = []
    for x in range(0, w, step):
        edge_pixels.append(px[x, 0])
        edge_pixels.append(px[x, h - 1])
    for y in range(0, h, step):
        edge_pixels.append(px[0, y])
        edge_pixels.append(px[w - 1, y])

    opaque_edge = [p for p in edge_pixels if p[3] > 24]
    if edge_pixels and len(opaque_edge) / len(edge_pixels) > 0.80:
        rs = [p[0] for p in opaque_edge]
        gs = [p[1] for p in opaque_edge]
        bs = [p[2] for p in opaque_edge]
        spread = max(max(rs) - min(rs), max(gs) - min(gs), max(bs) - min(bs))
        if spread < 40:
            # 边缘是均匀纯色 X。再看中心区域：若存在大量不透明且异色于 X 的像素，
            # 说明是"背景框 + 内部图标"；若中心也是 X 或透明，则是实心图形/环形，正常。
            mean = (sum(rs) // len(rs), sum(gs) // len(gs), sum(bs) // len(bs))
            x0, y0 = int(w * 0.25), int(h * 0.25)
            x1, y1 = int(w * 0.75), int(h * 0.75)
            total_center = 0
            diff_center = 0
            for cx in range(x0, x1, max(1, step // 2)):
                for cy in range(y0, y1, max(1, step // 2)):
                    p = px[cx, cy]
                    if p[3] > 24:
                        total_center += 1
                        if _color_dist(p, mean) > 40:
                            diff_center += 1
            if total_center > 0 and diff_center / total_center > 0.15:
                return ("BG", "边缘呈纯色边框且内部有异色内容（疑似残留背景），"
                        "尝试加 --remove-bg 或调大 --bg-tolerance")

    return "OK", ""


# ---------- 主流程 ----------

def main():
    p = argparse.ArgumentParser(description="把网格图标大图切成独立透明 PNG")
    p.add_argument("sheet", help="网格大图路径")
    p.add_argument("--rows", type=int, required=True, help="网格行数")
    p.add_argument("--cols", type=int, required=True, help="网格列数")
    p.add_argument("--names", help="图标名称，逗号分隔（行优先顺序）")
    p.add_argument("--names-file", help="名称文件：txt 每行一个，或 json 数组")
    p.add_argument("--outdir", required=True, help="输出目录")
    p.add_argument("--cell-size", type=int, default=512,
                   help="输出正方形画布边长（px），0 表示保持裁切后原始尺寸")
    p.add_argument("--padding", type=float, default=0.12,
                   help="使用 --cell-size 时，内容四周留白比例（0–0.4）")
    p.add_argument("--gap", type=int, default=0, help="单元格之间的间距（px），裁切时从四边扣除")
    p.add_argument("--no-trim", action="store_true", help="不自动裁掉透明边框")
    p.add_argument("--remove-bg", action="store_true", help="自动移除连通的纯色背景")
    p.add_argument("--bg-tolerance", type=int, default=32, help="背景移除色差容差（0–255）")
    args = p.parse_args()

    sheet_path = Path(args.sheet)
    if not sheet_path.exists():
        sys.exit(f"找不到大图: {sheet_path}")

    sheet = Image.open(sheet_path).convert("RGBA")
    W, H = sheet.size
    cw, ch = W // args.cols, H // args.rows
    if cw < 8 or ch < 8:
        sys.exit(f"单元格过小（{cw}x{ch}），检查 --rows/--cols 是否正确")

    names = parse_names(args)
    total = args.rows * args.cols
    if names is None:
        names = [f"icon_{i + 1}" for i in range(total)]
    if len(names) != total:
        sys.exit(f"名称数量({len(names)}) 与 网格数({total}) 不一致")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    results = []
    idx = 0
    for r in range(args.rows):
        for c in range(args.cols):
            left = c * cw + args.gap
            upper = r * ch + args.gap
            right = (c + 1) * cw - args.gap
            lower = (r + 1) * ch - args.gap
            cell = sheet.crop((left, upper, right, lower))
            raw_w, raw_h = cell.size

            if args.remove_bg:
                cell = remove_background(cell, tolerance=args.bg_tolerance)

            if not args.no_trim:
                bbox = cell.getbbox()
                if bbox is not None:
                    cell = cell.crop(bbox)

            # 自检在放画布前做：基于裁切后的真实内容边缘判断残留背景
            status, detail = self_check(cell, raw_w, raw_h)

            if args.cell_size > 0 and cell.getbbox() is not None:
                target = args.cell_size
                pad = int(target * min(max(args.padding, 0.0), 0.4))
                inner = target - 2 * pad
                cw2, ch2 = cell.size
                scale = min(inner / cw2, inner / ch2)
                new_size = (max(1, int(cw2 * scale)), max(1, int(ch2 * scale)))
                cell = cell.resize(new_size, Image.LANCZOS)
                canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
                canvas.paste(cell, ((target - new_size[0]) // 2,
                                    (target - new_size[1]) // 2), cell)
                cell = canvas

            name = names[idx]
            out_path = outdir / f"{name}.png"
            cell.save(out_path, "PNG")

            results.append((name, status, detail, out_path))
            idx += 1

    # 报告
    print(f"大图: {sheet_path.name}  {W}x{H}  网格 {args.rows}x{args.cols}  单元格 ~{cw}x{ch}")
    print(f"输出: {outdir}\n")
    ok_count = 0
    for name, status, detail, _ in results:
        mark = "OK " if status == "OK" else "XX "
        line = f"  [{mark}] {name}.png"
        if detail:
            line += f"  — {detail}"
        print(line)
        if status == "OK":
            ok_count += 1
    print(f"\n达标 {ok_count}/{len(results)}")
    if ok_count != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
