#!/usr/bin/env python3
"""
chroma_key.py — 智能纯色背景抠图，输出透明、居中、正方形 PNG。

设计原则（来自 huashu-icon-set 血泪教训）：
- AI 生图不输出真正的透明背景，必须生成纯色背景再代码抠除。
- 绿色背景用绿色键控（chroma key），精确且不会误删白色底座。
- 蓝色背景用蓝色键控（用于含绿色的图标，如微信）。
- 其他背景用 numpy 形态学 flood fill 从四边移除连通背景。
- 边缘 despill 去除背景色溢出，高斯模糊抗锯齿。
- 自动 trim 透明边缘 + 居中到正方形画布。

背景色选择策略：
- 普通图标 → 纯绿色 #00FF00（绿色键控，对投影最鲁棒）
- 含绿色的品牌色图标（微信等）→ 纯蓝色 #0000FF（蓝色键控）
- 禁止品红/黄色背景 + flood fill：方向性投影会形成渐变色带，
  容差小了有残留，大了误删图标，不可靠。

用法：
    python3 chroma_key.py <input_dir> <output_dir> [--size 512] [--padding 0.12]
    python3 chroma_key.py <input.png> <output.png> --single [--size 512] [--tolerance 55]

依赖：Pillow + numpy（必需）。
"""
import os
import sys
import argparse

import numpy as np
from PIL import Image, ImageFilter

# ---------- 背景检测 ----------

def detect_bg_color(arr):
    """从图片四角和边缘取样，返回背景主色 (r,g,b)。"""
    h, w = arr.shape[:2]
    samples = []
    edge = 30
    for y in range(0, edge, 3):
        for x in range(0, edge, 3):
            samples.append(arr[y, x, :3])
            samples.append(arr[y, w - 1 - x, :3])
            samples.append(arr[h - 1 - y, x, :3])
            samples.append(arr[h - 1 - y, w - 1 - x, :3])
    return tuple(int(v) for v in np.median(np.array(samples), axis=0))


def classify_bg(bg):
    """判断背景类型：'green' | 'blue' | 'other'。"""
    br, bg_c, bb = bg
    if bg_c > br + 30 and bg_c > bb + 30 and bg_c > 100:
        return 'green'
    if bb > br + 30 and bb > bg_c + 30 and bb > 100:
        return 'blue'
    return 'other'


# ---------- 颜色键控 ----------

def _chroma_key(arr, dominant_channel, thresh=80, margin=25):
    """通用颜色键控。dominant_channel: 0=红, 1=绿, 2=蓝。"""
    channels = [arr[:, :, c].astype(np.int16) for c in range(3)]
    dom = channels[dominant_channel]
    others = [channels[c] for c in range(3) if c != dominant_channel]

    bg_mask = (dom > thresh) & (dom > others[0] + margin) & (dom > others[1] + margin)
    alpha = np.where(bg_mask, 0, 255).astype(np.uint8)
    alpha = np.array(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(radius=1.2)))
    arr[:, :, 3] = alpha

    # Despill：半透明边缘像素的主色通道不超过其他两通道较小值 + 8
    edge = (alpha > 0) & (alpha < 255)
    min_other = np.minimum(others[0], others[1])
    despilled = np.minimum(dom, min_other + 8)
    arr[:, :, dominant_channel] = np.where(edge, despilled, arr[:, :, dominant_channel]).astype(np.uint8)
    return arr


def key_green(arr, **kw):
    """绿色背景颜色键控。"""
    return _chroma_key(arr, 1, **kw)


def key_blue(arr, **kw):
    """蓝色背景颜色键控（用于含绿色的图标）。"""
    return _chroma_key(arr, 2, **kw)


# ---------- Flood fill（numpy 形态学，不依赖 scipy）----------

def key_floodfill(arr, tolerance=55):
    """Flood fill 从四边移除连通背景。用 numpy 形态学膨胀实现。"""
    h, w = arr.shape[:2]
    bg_ref = np.array(detect_bg_color(arr), dtype=np.int16)

    r = arr[:, :, 0].astype(np.int16)
    g = arr[:, :, 1].astype(np.int16)
    b = arr[:, :, 2].astype(np.int16)
    dist = np.abs(r - bg_ref[0]) + np.abs(g - bg_ref[1]) + np.abs(b - bg_ref[2])
    candidate = dist <= tolerance

    # 从四边 seed
    mask = np.zeros((h, w), dtype=bool)
    mask[0, :] = candidate[0, :]
    mask[-1, :] = candidate[-1, :]
    mask[:, 0] = candidate[:, 0]
    mask[:, -1] = candidate[:, -1]

    # 迭代膨胀直到收敛
    for _ in range(2000):
        dilated = mask.copy()
        dilated[1:, :] |= mask[:-1, :]
        dilated[:-1, :] |= mask[1:, :]
        dilated[:, 1:] |= mask[:, :-1]
        dilated[:, :-1] |= mask[:, 1:]
        new_mask = dilated & candidate
        if np.array_equal(new_mask, mask):
            break
        mask = new_mask

    alpha = np.where(mask, 0, 255).astype(np.uint8)
    alpha = np.array(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(radius=1.2)))
    arr[:, :, 3] = alpha

    # Despill：通用边缘去色溢（压低与背景主色最接近的通道）
    edge = (alpha > 0) & (alpha < 255)
    bg_dom = int(np.argmax(bg_ref))
    other_channels = [c for c in range(3) if c != bg_dom]
    min_other = np.minimum(arr[:, :, other_channels[0]].astype(np.int16),
                           arr[:, :, other_channels[1]].astype(np.int16))
    despilled = np.minimum(arr[:, :, bg_dom].astype(np.int16), min_other + 8)
    arr[:, :, bg_dom] = np.where(edge, despilled, arr[:, :, bg_dom]).astype(np.uint8)
    return arr


# ---------- 后处理 ----------

def trim_and_center(img, size=512, padding=0.12):
    """裁掉透明边缘，等比缩放并居中到正方形画布。"""
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    content_max = int(size * (1 - 2 * padding))
    cw, ch = img.size
    if cw == 0 or ch == 0:
        return Image.new('RGBA', (size, size), (0, 0, 0, 0))
    scale = min(content_max / cw, content_max / ch)
    nw, nh = max(1, int(cw * scale)), max(1, int(ch * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - nw) // 2, (size - nh) // 2), img)
    return canvas


def self_check(img):
    """自检：返回 (status, info)。status: OK / BG / SMALL。"""
    arr = np.array(img)
    corners = [int(arr[0, 0, 3]), int(arr[0, -1, 3]),
               int(arr[-1, 0, 3]), int(arr[-1, -1, 3])]
    opaque_ratio = float(np.mean(arr[:, :, 3] > 128))
    if max(corners) > 20:
        return 'BG', f'corner_alphas={corners}'
    if opaque_ratio < 0.02:
        return 'SMALL', f'opaque_ratio={opaque_ratio:.3f}'
    return 'OK', f'opaque_ratio={opaque_ratio:.3f}'


# ---------- 主流程 ----------

def process_image(input_path, output_path, size=512, padding=0.12, tolerance=55):
    """处理单张图片：抠图 + trim + 居中 + 保存 + 自检。"""
    img = Image.open(input_path).convert('RGBA')
    arr = np.array(img)

    bg = detect_bg_color(arr)
    bg_type = classify_bg(bg)

    if bg_type == 'green':
        arr = key_green(arr)
    elif bg_type == 'blue':
        arr = key_blue(arr)
    else:
        arr = key_floodfill(arr, tolerance=tolerance)

    result = Image.fromarray(arr, 'RGBA')
    result = trim_and_center(result, size=size, padding=padding)
    result.save(output_path)

    status, info = self_check(result)
    return status, bg_type, bg, info


def main():
    ap = argparse.ArgumentParser(description='纯色背景抠图 → 透明居中 PNG')
    ap.add_argument('input', help='输入目录（批量模式）或输入图片路径（single 模式）')
    ap.add_argument('output', help='输出目录或输出图片路径')
    ap.add_argument('--size', type=int, default=512, help='输出正方形边长')
    ap.add_argument('--padding', type=float, default=0.12, help='内容四周留白比例')
    ap.add_argument('--tolerance', type=int, default=55, help='flood fill 容差（非绿/蓝背景时）')
    ap.add_argument('--single', action='store_true', help='单文件模式')
    args = ap.parse_args()

    if args.single or args.input.lower().endswith('.png'):
        status, bg_type, bg, info = process_image(
            args.input, args.output, size=args.size,
            padding=args.padding, tolerance=args.tolerance)
        print(f'[{status}] {os.path.basename(args.input)}  bg={bg} ({bg_type})  {info}')
        sys.exit(0 if status == 'OK' else 1)

    os.makedirs(args.output, exist_ok=True)
    files = sorted(f for f in os.listdir(args.input) if f.lower().endswith('.png'))
    ok = 0
    for f in files:
        name = os.path.splitext(f)[0]
        out_path = os.path.join(args.output, f'{name}.png')
        status, bg_type, bg, info = process_image(
            os.path.join(args.input, f), out_path,
            size=args.size, padding=args.padding, tolerance=args.tolerance)
        print(f'  [{status}] {name}.png  ({bg_type})  {info}')
        if status == 'OK':
            ok += 1
    print(f'\n达标 {ok}/{len(files)}')
    sys.exit(0 if ok == len(files) else 1)


if __name__ == '__main__':
    main()
