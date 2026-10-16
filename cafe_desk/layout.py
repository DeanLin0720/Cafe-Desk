"""共用版面常數、烘焙度色調

各咖啡機的位置（機身原點、沖煮頭、杯子、磨豆區、蒸氣管）定義在 machines/ 裡；
這裡只放所有機器共用的尺寸。
"""
from .gfx import mix
from .util import clamp

WIN_H = 444                         # 場景高度（場景寬度由咖啡機決定）
TOP_PAD = 136                       # 場景上方的透明區，放萃取曲線與拉花卡片
FLOOR = 364                         # 檯面（場景座標）：咖啡機底部

# 把手（以濾杯左上角為原點的相對座標）
PF_BASKET_W = 72                    # 濾杯外緣寬度
PF_BASKET_H = 24                    # 直筒濾杯高度
PF_TIPS = (26, 46)                  # Y 型出水嘴兩個出口的 x
PF_TIP_Y = 33                       # 出口的 y

C_DARK, C_MID, C_TIGER, C_BLOND = "#2b1408", "#7a3d16", "#c27a3a", "#d6a96c"

# 烘焙度色調：液體深色/琥珀色、流柱偏色、crema 偏色、金黃化終點色
# 咖啡豆顏色（豆倉）：(暗, 亮, 中線)
BEAN_COLORS = {"淺焙": ("#6a3a1c", "#9a5e30", "#3a1e0e"), "中焙": ("#3a1e0e", "#6a3a1c", "#1a0c05"),
               "深焙": ("#1e0f07", "#3a2012", "#0a0503")}

ROAST_LOOK = {
    "淺焙": {"deep": "#2a120a", "amber": "#8f4a24", "tint": "#b8602a", "tint_k": 0.18,
             "crema": "#d29a5c", "blond": "#dcb070"},
    "中焙": {"deep": "#1c0d06", "amber": "#6e3a1c", "tint": "#7a3d16", "tint_k": 0.0,
             "crema": "#b8763c", "blond": "#d6a96c"},
    "深焙": {"deep": "#110805", "amber": "#4a2616", "tint": "#1a0d07", "tint_k": 0.22,
             "crema": "#8a4c26", "blond": "#b88a58"},
}


def liquid_look(roast, tds, ey_short):
    """依烘焙度、濃度(TDS)、萃取不足程度，回傳 (上層色, 底層色, 不透明度)"""
    look = ROAST_LOOK[roast]
    k = clamp((tds - 5.0) / 8.0, 0, 1)            # TDS 5% 很淡 → 13% 很濃
    k = k * (1 - 0.35 * ey_short)                 # 萃取不足再淡一點
    top = mix(look["amber"], look["deep"], 0.10 + 0.60 * k)
    bottom = mix(look["amber"], look["deep"], 0.40 + 0.60 * k)
    alpha = int(255 * (0.72 + 0.28 * k))          # 淡的咖啡比較透，看得到杯子後方
    return top, bottom, alpha


def bar_angle(bar):
    return 225 - bar / 12 * 270


def dial_angle(v, vmin, vmax):
    """錶盤刻度：最小值在左下 225°，最大值在右下 -45°"""
    return 225 - clamp((v - vmin) / (vmax - vmin), 0, 1) * 270
