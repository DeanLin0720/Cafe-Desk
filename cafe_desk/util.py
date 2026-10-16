"""共用的小工具"""


def clamp(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))


def lerp(a, b, t):
    return a + (b - a) * t

