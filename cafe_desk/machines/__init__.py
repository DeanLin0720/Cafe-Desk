"""咖啡機清單：右鍵選單「咖啡機」可切換"""
from .allinone import AllInOne
from .compact import Compact
from .desk01 import Desk01
from .duo import Duo
from .lever import Lever

MACHINES = {m.key: m for m in (Desk01(), Lever(), Compact(), AllInOne(), Duo())}
DEFAULT_MACHINE = "desk01"
