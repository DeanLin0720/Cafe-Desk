"""比較兩組 render_frames.py 的畫面：有差異的張數、像素數、最大色差（0–255）

    python tools/compare_frames.py <資料夾 A> <資料夾 B>
"""
import sys, glob, os
from PySide6.QtGui import QImage
a, b = sys.argv[1], sys.argv[2]
tot = worst = 0; worst_f = None; changed = 0
for f in sorted(glob.glob(f"{a}/*.png")):
    x = QImage(f).convertToFormat(QImage.Format_ARGB32); y = QImage(f.replace(a, b, 1)).convertToFormat(QImage.Format_ARGB32)
    bx, by = bytes(x.constBits()), bytes(y.constBits())
    if bx == by: continue
    changed += 1
    n = 0; m = 0
    for i in range(0, len(bx), 4):
        if bx[i:i+4] != by[i:i+4]:
            n += 1; m = max(m, max(abs(bx[i+j] - by[i+j]) for j in range(4)))
    tot += n
    if m > worst: worst, worst_f = m, os.path.basename(f)
print(f"changed frames {changed}, changed px {tot}, max channel diff {worst} ({worst_f})")
