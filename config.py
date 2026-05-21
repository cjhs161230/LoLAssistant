"""LoL 智能选人助手 - 配置常量"""

import os
from pathlib import Path

# 路径
ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
ASSETS_DIR = ROOT_DIR / "assets"

# LCU
LCU_LOCKFILE_CANDIDATES = [
    r"C:\Riot Games\League of Legends\lockfile",
    r"D:\Riot Games\League of Legends\lockfile",
    r"E:\Riot Games\League of Legends\lockfile",
    r"C:\Program Files\Riot Games\League of Legends\lockfile",
    r"C:\Program Files (x86)\Riot Games\League of Legends\lockfile",
    r"E:\WeGameApps\英雄联盟\LeagueClient\lockfile",
]

# LCU API 轮询间隔（秒）
CHAMP_SELECT_POLL_INTERVAL = 3

# 推荐权重
WEIGHTS = {
    "meta": 0.40,
    "counter": 0.30,
    "personal": 0.20,
    "team": 0.10,
}

# 版本强度分映射
TIER_SCORE = {
    "OP": 100, "1": 100,
    "S":   95,
    "A":   85, "2": 85,
    "B":   70, "3": 70,
    "C":   55, "4": 55,
    "D":   40, "5": 40,
}
TIER_DEFAULT_SCORE = 30

# 数据源
DATA_SOURCE = "op.gg"  # op.gg 或 u.gg
OPGG_REGION = "cn"     # 国服
CACHE_TTL_HOURS = 24

# 爬虫
REQUEST_DELAY_MIN = 2.0
REQUEST_DELAY_MAX = 5.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# 个人数据
PERSONAL_GAMES_THRESHOLD = 20
PERSONAL_GAMES_LOW = 5
PERSONAL_DEFAULT_SCORE = 30
PERSONAL_NO_DATA_SCORE = 30

# 团队适配
TEAM_BONUS_AP = 20
TEAM_BONUS_TANK = 20
TEAM_BONUS_CC = 20
TEAM_SCORE_MAX = 100

# 候选池
CANDIDATE_POOL_EMPTY_FALLBACK = True
POSITION_DEFAULT = "MID"
