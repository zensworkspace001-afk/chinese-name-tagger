# -*- coding: utf-8 -*-
"""產生選單列三種狀態用的極簡圖示（不是從使用者的照片去背，是直接用向量
畫的，線條粗細/尺寸抓得比較保守，確保縮到 18-22pt 選單列大小還看得清楚）：

  status_ready_icon.png    就緒：六芒雪花/星芒（跟 CNT 品牌雪花意象呼應）
  status_starting_icon.png 啟動中：三個小圓點（常見的「載入中」視覺語言）
  status_error_icon.png    錯誤：三角形驚嘆號（跟 ⚠️ 同樣語意，但線條風格
                            跟另外兩個圖示統一）

三個圖形輪廓差異夠大（放射狀線條 vs. 三個離散小點 vs. 三角形實心），就算
縮很小、只看剪影也分得出來是哪個狀態。用超取樣（畫大尺寸再縮小）讓邊緣
反鋸齒乾淨。

跑法：cd desktop_tagger/mac && ./build_venv/bin/python3 _build_status_icons.py
"""
import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

SUPER = 8  # 超取樣倍率
OUT_SIZE = 60  # 最終輸出尺寸（px），選單列會依 pt 需求自動縮放
CANVAS = OUT_SIZE * SUPER


def new_canvas():
    return Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))


def save(img, name):
    small = img.resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS)
    small.save(os.path.join(HERE, name))
    print("saved", name)


def draw_ready():
    """六芒星芒雪花：從中心放射 6 條線，線條中段到尾端加一點漸細/端點圓
    球，呼應原本雪花意象，但只有 6 條主線、沒有子分支，縮小才不會糊掉。"""
    img = new_canvas()
    d = ImageDraw.Draw(img)
    cx, cy = CANVAS // 2, CANVAS // 2
    r_outer = CANVAS * 0.42
    r_inner = CANVAS * 0.10
    stroke = int(CANVAS * 0.075)
    for i in range(6):
        angle = math.radians(i * 60 - 90)
        x0 = cx + r_inner * math.cos(angle)
        y0 = cy + r_inner * math.sin(angle)
        x1 = cx + r_outer * math.cos(angle)
        y1 = cy + r_outer * math.sin(angle)
        d.line([(x0, y0), (x1, y1)], fill=(0, 0, 0, 255), width=stroke)
        # 尾端小圓點，呼應電路板意象
        tip_r = stroke * 0.55
        d.ellipse(
            [x1 - tip_r, y1 - tip_r, x1 + tip_r, y1 + tip_r], fill=(0, 0, 0, 255)
        )
    # 中心實心圓
    center_r = CANVAS * 0.09
    d.ellipse(
        [cx - center_r, cy - center_r, cx + center_r, cy + center_r],
        fill=(0, 0, 0, 255),
    )
    save(img, "status_ready_icon.png")


def draw_starting():
    """三個橫排小圓點，經典「載入中」語彙，跟放射狀的 ready 圖示、
    三角形的 error 圖示在剪影上明顯不同。"""
    img = new_canvas()
    d = ImageDraw.Draw(img)
    cy = CANVAS // 2
    r = CANVAS * 0.09
    spacing = CANVAS * 0.30
    for i in (-1, 0, 1):
        cx = CANVAS // 2 + i * spacing
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 255))
    save(img, "status_starting_icon.png")


def draw_error():
    """三角形驚嘆號，跟系統 ⚠️ 同樣語意，但線條風格（黑色剪影、無填色
    細節）跟另外兩個圖示統一，維持整組圖示風格一致。"""
    img = new_canvas()
    d = ImageDraw.Draw(img)
    cx, cy = CANVAS // 2, CANVAS // 2
    half = CANVAS * 0.38
    top = (cx, cy - half)
    bl = (cx - half * 0.95, cy + half * 0.75)
    br = (cx + half * 0.95, cy + half * 0.75)
    stroke = int(CANVAS * 0.075)
    d.line([top, br, bl, top], fill=(0, 0, 0, 255), width=stroke, joint="curve")
    # 驚嘆號：直條 + 下方小圓點
    bar_w = CANVAS * 0.065
    bar_top = cy - half * 0.28
    bar_bottom = cy + half * 0.12
    d.rounded_rectangle(
        [cx - bar_w / 2, bar_top, cx + bar_w / 2, bar_bottom],
        radius=bar_w / 2,
        fill=(0, 0, 0, 255),
    )
    dot_r = bar_w * 0.65
    dot_cy = cy + half * 0.32
    d.ellipse(
        [cx - dot_r, dot_cy - dot_r, cx + dot_r, dot_cy + dot_r],
        fill=(0, 0, 0, 255),
    )
    save(img, "status_error_icon.png")


if __name__ == "__main__":
    draw_ready()
    draw_starting()
    draw_error()
