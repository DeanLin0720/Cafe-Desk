"""豆子管理：產地、烘焙度、風味，一包豆子的烘焙日與剩餘克數

養豆天數＝今天（真實日期）－烘焙日，每天自動增加；豆倉存量＝這包剩下的克數。
豆子用完要「開新包」（右鍵「豆子」），自動模式的咖啡師會自己開。
"""
import datetime
import random

from .festivals import today

# key：(產地名稱, 烘焙度, 風味, 甜感加成)
ORIGINS = {
    "yirgacheffe": ("衣索比亞 耶加雪菲", "淺焙", "茉莉花香、柑橘", 0.4),
    "kenya": ("肯亞 AA", "淺焙", "黑醋栗、明亮果酸", 0.1),
    "colombia": ("哥倫比亞 薇拉", "中焙", "焦糖、紅莓", 0.3),
    "guatemala": ("瓜地馬拉 安提瓜", "中焙", "可可、香料", 0.2),
    "house": ("桌上綜合配方", "中焙", "堅果、牛奶巧克力", 0.25),
    "brazil": ("巴西 喜拉朵", "深焙", "堅果、黑巧克力", 0.15),
    "sumatra": ("印尼 曼特寧", "深焙", "草本、黑糖、厚實", 0.0),
}
BAG_G = 250.0


def new_bag(origin=None, rnd=random):
    """開一包新豆子：烘焙日在 2–9 天前（剛買回來的新鮮豆）"""
    origin = origin if origin in ORIGINS else rnd.choice(list(ORIGINS))
    roasted = today() - datetime.timedelta(days=rnd.randint(2, 9))
    return {"origin": origin, "roasted": roasted.isoformat(), "left": BAG_G, "size": BAG_G}


def valid_bag(bag):
    try:
        datetime.date.fromisoformat(bag["roasted"])
        return bag["origin"] in ORIGINS and float(bag["left"]) >= 0
    except Exception:
        return False


def bag_age(bag):
    """烘焙後第幾天（至少 1）"""
    roasted = datetime.date.fromisoformat(bag["roasted"])
    return max(1, (today() - roasted).days)


def bag_roast(bag):
    return ORIGINS[bag["origin"]][1]


def bag_name(bag):
    return ORIGINS[bag["origin"]][0]


def bag_flavor(bag):
    return ORIGINS[bag["origin"]][2]


def sweet_bonus(origin):
    o = ORIGINS.get(origin)
    return o[3] if o else 0.0
