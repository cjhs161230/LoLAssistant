"""Flask 后端 — 为 Vue3 前端提供 API 服务"""

import json
import logging
import sys
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from config import DATA_DIR
from meta_fetcher import MetaFetcher
from recommendation_engine import RecommendationEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("server")

app = Flask(__name__, static_folder="static")

# ── 初始化 ──────────────────────────────────────────

DATA_DIR.mkdir(parents=True, exist_ok=True)
fetcher = MetaFetcher()
engine = RecommendationEngine()

# 启动时预加载
logger.info("加载 Tier 数据...")
meta_data = fetcher.get_tier_list()
tier_list = meta_data.get("tier_list", {})
logger.info("已加载 %d 个位置", len(tier_list))

logger.info("加载 Counter 缓存...")
cache_file = DATA_DIR / "counter_cache.json"
counter_cache: dict = {}
if cache_file.exists():
    try:
        with open(cache_file, encoding="utf-8") as f:
            counter_cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
logger.info("Counter 缓存: %d 个英雄", len(counter_cache))

# 英雄映射
en_to_id: dict[str, int] = {}
cn_to_en: dict[str, str] = {}  # 中文名 → 英文名
id_to_info: dict[int, dict] = {}

cn_path = DATA_DIR / "champion_names_cn.json"
if cn_path.exists():
    with open(cn_path, encoding="utf-8") as f:
        cn_data = json.load(f)
    for en_name, info in cn_data.items():
        if isinstance(info, dict):
            cid = info.get("id", 0)
            cn = info.get("name_cn", en_name)
            en_to_id[en_name] = cid
            en_to_id[en_name.lower()] = cid
            cn_to_en[cn] = en_name
            # 外号也映射
            for term in info.get("search_terms", []):
                cn_to_en[term] = en_name
            id_to_info[cid] = {
                "id": cid,
                "en_name": en_name,
                "cn_name": cn,
                "search_terms": info.get("search_terms", []),
            }

candidates = [v.get("id") for v in engine._attributes.values() if v.get("id")] or list(range(1, 200))


# ── API 路由 ────────────────────────────────────────

@app.route("/api/champions")
def api_champions():
    """返回全部英雄列表（用于前端搜索）"""
    result = []
    for cid, info in id_to_info.items():
        result.append({
            "id": cid,
            "en_name": info["en_name"],
            "cn_name": info["cn_name"],
            "search_terms": info["search_terms"],
        })
    result.sort(key=lambda x: x["cn_name"])
    return jsonify(result)


@app.route("/api/tier-list")
def api_tier_list():
    """返回版本 Tier 数据（当前为全段位聚合，OP.GG API 不支持按段位过滤）"""
    return jsonify(tier_list)


@app.route("/api/meta-info")
def api_meta_info():
    """返回元数据"""
    return jsonify({
        "last_updated": meta_data.get("last_updated"),
        "patch": meta_data.get("patch", ""),
        "rank_filter_available": False,  # OP.GG API 暂不支持
        "note": "数据为全段位聚合",
    })


@app.route("/api/personal", methods=["GET", "POST"])
def api_personal():
    """个人擅长英雄数据"""
    path = DATA_DIR / "personal_champions.json"
    if request.method == "GET":
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return jsonify(json.load(f))
        return jsonify({"champions": []})

    if request.method == "POST":
        data = request.get_json()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True})


@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    """生成推荐"""
    global counter_cache
    data = request.get_json() or {}

    position = data.get("position", "MID")
    enemy_names = data.get("enemy_names", [])  # 英文名列表
    team_names = data.get("team_names", [])
    ban_names = data.get("ban_names", [])

    enemy_ids = [en_to_id.get(n, en_to_id.get(n.lower(), 0)) for n in enemy_names]
    team_ids = [en_to_id.get(n, en_to_id.get(n.lower(), 0)) for n in team_names]
    ban_ids = [en_to_id.get(n, en_to_id.get(n.lower(), 0)) for n in ban_names]
    enemy_ids = [i for i in enemy_ids if i]
    team_ids = [i for i in team_ids if i]
    ban_ids = [i for i in ban_ids if i]

    if not enemy_ids:
        return jsonify({"error": "请至少添加一个对手英雄"}), 400

    # 按需拉取 Counter 数据
    for eid in enemy_ids:
        name = engine._champ_name(eid).lower()
        if name and name not in counter_cache:
            logger.info("拉取 %s Counter 数据...", name)
            result = fetcher.get_counter_data(name.capitalize())
            if result:
                counter_cache[name] = result
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(counter_cache, f, ensure_ascii=False, indent=2)

    # 加载个人数据
    personal = None
    pp = DATA_DIR / "personal_champions.json"
    if pp.exists():
        with open(pp, encoding="utf-8") as f:
            pdata = json.load(f)
            champions = pdata.get("champions", [])
            if champions:
                personal = {"champions": champions}

    result = engine.recommend(
        candidates=candidates,
        position=position,
        enemy_champs=enemy_ids,
        team_champs=team_ids,
        bans=ban_ids,
        tier_list=tier_list,
        counter_data=counter_cache,
        personal_data=personal,
        owned_champs=None,
    )
    return jsonify(result)


@app.route("/api/preload", methods=["POST"])
def api_preload():
    """预加载 Counter 数据"""
    global counter_cache
    data = request.get_json() or {}
    names = data.get("names", [])
    if names:
        fetcher.preload_counters_batch(names, max_workers=5)
        with open(cache_file, encoding="utf-8") as f:
            counter_cache = json.load(f)
    return jsonify({"cached": len(counter_cache)})


@app.route("/api/stats")
def api_stats():
    """返回缓存统计"""
    return jsonify({
        "tier_positions": len(tier_list),
        "counter_cached": len(counter_cache),
        "champions": len(id_to_info),
        "personal": (DATA_DIR / "personal_champions.json").exists(),
    })


# ── 前端静态文件 ────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


# ── 入口 ────────────────────────────────────────────

def start_server(port: int = 5732, open_browser: bool = True):
    """启动 Flask 服务器"""
    url = f"http://127.0.0.1:{port}"
    if open_browser:
        webbrowser.open(url)
    logger.info("LoL 选人助手 Web 版: %s", url)
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    start_server()
