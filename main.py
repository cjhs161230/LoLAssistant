#!/usr/bin/env python3
"""LoL 智能选人助手 - 手动模式为主入口"""

import json
import logging
import sys
import threading

import PySimpleGUI as sg

from config import DATA_DIR
from meta_fetcher import MetaFetcher
from recommendation_engine import RecommendationEngine
from gui import (
    CN_DATA,
    DISPLAY_LIST,
    LANE_CN,
    LolAssistantGUI,
    add_to_list,
    clear_list,
    get_en_name,
    get_en_names_from_selected,
    remove_from_list,
    update_hero_list,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

MODE = "web"  # 默认 Web 模式
if "--manual" in sys.argv:
    MODE = "manual"
elif "--demo" in sys.argv:
    MODE = "demo"
elif "--lcu" in sys.argv:
    MODE = "lcu"
elif "--download-all" in sys.argv:
    MODE = "download-all"


def init():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    mode_label = {"web": "Web 模式", "manual": "手动模式", "demo": "演示模式",
                  "lcu": "LCU模式", "download-all": "全量数据下载"}
    logger.info("LoL 智能选人助手 v1.0 [%s]", mode_label.get(MODE, MODE))


def build_en_to_id() -> dict[str, int]:
    """构建英文英雄名 → ID 映射 (从 CN_DATA)"""
    result = {}
    for en_name, info in CN_DATA.items():
        if isinstance(info, dict):
            result[en_name] = info.get("id", 0)
        else:
            result[en_name] = 0
    return result


def parse_position(values: dict) -> str:
    """从 Radio 值中解析位置"""
    for pos in ("TOP", "JUNGLE", "MID", "BOTTOM", "UTILITY"):
        if values.get(f"-POS-{pos}-"):
            return pos
    return "MID"


def query_personal_data(fetcher: MetaFetcher) -> list[dict] | None:
    """弹出输入框查询 OP.GG 召唤师个人数据"""
    layout = [
        [sg.Text("请输入你的召唤师信息查询个人数据", font=("Microsoft YaHei", 11))],
        [sg.Text("召唤师名称"), sg.Input(key="-NAME-", size=(20, 1))],
        [sg.Text("Tag (#后面) "), sg.Input(key="-TAG-", size=(10, 1),
                                          default_text="CN1")],
        [sg.Text("服务器"), sg.Combo(["cn", "kr"], default_value="cn",
                                    key="-REGION-", size=(6, 1))],
        [sg.Button("查询"), sg.Button("取消")],
    ]
    win = sg.Window("查询个人数据", layout, finalize=True)
    event, values = win.read()
    win.close()

    if event != "查询":
        return None

    game_name = values.get("-NAME-", "").strip()
    tag_line = values.get("-TAG-", "").strip()
    region = values.get("-REGION-", "cn")

    if not game_name:
        sg.popup("请输入召唤师名称")
        return None

    stats = fetcher.get_summoner_champions(game_name, tag_line, region)
    if stats:
        sg.popup(f"已加载 {len(stats)} 个英雄的个人数据")
        return stats
    else:
        sg.popup("未能查询到个人数据，请确认名称和Tag正确")
        return None


def _load_personal_champions() -> list[dict] | None:
    """加载本地个人英雄数据"""
    path = DATA_DIR / "personal_champions.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("champions", [])
    except (json.JSONDecodeError, OSError):
        return None


def _extract_top_champions(tier_list: dict, top_n: int = 12) -> list[str]:
    """从 Tier 列表中提取各位置 Top N 热门英雄，去重后返回英文名列表"""
    seen = set()
    result = []
    # 按位置依次取 Top N
    for pos in ("MID", "TOP", "JUNGLE", "BOTTOM", "UTILITY"):
        heroes = tier_list.get(pos, [])
        # 按 tier 升序（越小越强），再按胜率降序
        sorted_heroes = sorted(
            heroes,
            key=lambda h: (int(h.get("tier", 99)), -float(h.get("winRate", 0)))
        )
        for h in sorted_heroes[:top_n]:
            name = h.get("name", "")
            if name and name not in seen:
                seen.add(name)
                result.append(name)
    logger.info("从 Tier 列表提取 %d 个热门英雄用于预加载", len(result))
    return result


def manual_main():
    """手动模式：用户填写选人信息，程序给出推荐"""
    gui = LolAssistantGUI()
    fetcher = MetaFetcher()
    engine = RecommendationEngine()
    en_to_id = build_en_to_id()

    # 1. 预加载版本数据
    logger.info("预加载版本 Tier 数据...")
    meta_data = fetcher.get_tier_list()
    tier_list = meta_data.get("tier_list", {})
    logger.info("已加载 %d 个位置的 Tier 数据", len(tier_list))

    # 2. 加载 Counter 缓存
    logger.info("加载 Counter 缓存...")
    counter_cache: dict = {}
    cache_file = DATA_DIR / "counter_cache.json"
    if cache_file.exists():
        try:
            with open(cache_file, encoding="utf-8") as f:
                counter_cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            counter_cache = {}
    logger.info("Counter 缓存中有 %d 个英雄的数据", len(counter_cache))

    # 3. 加载个人英雄数据
    personal_data = _load_personal_champions()
    if personal_data:
        logger.info("已加载 %d 个擅长英雄的个人数据", len(personal_data))

    # 4. 全英雄 ID 列表作为候选池
    candidates = [v.get("id") for v in engine._attributes.values() if v.get("id")]
    if not candidates:
        candidates = list(range(1, 200))

    # 5. 从 Tier 列表提取热门英雄，启动后台预加载
    top_champs = _extract_top_champions(tier_list)
    preload_state = {"done": len(counter_cache) >= len(top_champs),
                     "status": "", "total": len(top_champs)}

    if not preload_state["done"] and top_champs:
        def _preload_worker():
            def progress(done, total, name):
                preload_state["status"] = f"预加载中: {done}/{total}"
            result = fetcher.preload_counters_batch(
                top_champs, on_progress=progress, max_workers=5
            )
            # 合并回主线程用的 counter_cache
            for k, v in result.items():
                counter_cache[k] = v
            preload_state["done"] = True
            preload_state["status"] = f"已缓存 {len(counter_cache)} 个英雄Counter数据"
            logger.info(preload_state["status"])

        threading.Thread(target=_preload_worker, daemon=True).start()
        logger.info("后台预加载 %d 个热门英雄 Counter 数据...", preload_state["total"])

    # 6. 显示手动模式窗口
    window = gui.show_manual_mode()
    if preload_state["status"]:
        window["-STATUS-"].update(preload_state["status"])

    logger.info("手动模式就绪，等待用户输入...")
    logger.info("提示：搜索框支持中文名、英文名、外号（如：盲僧、瞎子、奥巴马、压缩...）")

    while True:
        event, values = window.read(timeout=500)  # 500ms 超时以更新预加载状态

        # 更新预加载进度
        if preload_state["status"] and not preload_state["done"]:
            window["-STATUS-"].update(preload_state["status"])
        elif preload_state["done"] and preload_state["status"]:
            window["-STATUS-"].update(preload_state["status"])
            preload_state["status"] = ""  # 只显示一次"已完成"

        if event == sg.WIN_CLOSED:
            break

        # ── 搜索过滤 ──
        if event == "-SEARCH-":
            query = values["-SEARCH-"]
            update_hero_list(window, "-HERO-LIST-", query)

        # ── 双击英雄列表 = 快速加到对手 ──
        if event == "-HERO-LIST-" and values["-HERO-LIST-"]:
            # 双击不会触发 event，只有单击 + 回车才会。这里仅做选择。
            pass

        # ── 添加到对手 ──
        if event == "-ADD-ENEMY-":
            selected = values.get("-HERO-LIST-")
            if selected:
                hero = selected[0]
                add_to_list(window, "-ENEMY-LIST-", hero, max_count=5)

        # ── 添加到我方 ──
        if event == "-ADD-TEAM-":
            selected = values.get("-HERO-LIST-")
            if selected:
                hero = selected[0]
                add_to_list(window, "-TEAM-LIST-", hero, max_count=4)

        # ── 添加到Ban ──
        if event == "-ADD-BAN-":
            selected = values.get("-HERO-LIST-")
            if selected:
                hero = selected[0]
                add_to_list(window, "-BAN-LIST-", hero, max_count=10)

        # ── 移除 ──
        if event == "-RM-ENEMY-":
            remove_from_list(window, "-ENEMY-LIST-")
        if event == "-RM-TEAM-":
            remove_from_list(window, "-TEAM-LIST-")
        if event == "-RM-BAN-":
            remove_from_list(window, "-BAN-LIST-")

        # ── 清空 ──
        if event == "-CLR-ENEMY-":
            clear_list(window, "-ENEMY-LIST-")
        if event == "-CLR-TEAM-":
            clear_list(window, "-TEAM-LIST-")
        if event == "-CLR-BAN-":
            clear_list(window, "-BAN-LIST-")

        # ── 回车键在搜索框 → 快捷添加到对手 ──
        if event == "-SEARCH-" and values.get("-SEARCH-"):
            # pg 不直接支持回车事件，通过 bind_return_key 在按钮上处理
            pass

        # ── 生成推荐 ──
        if event == "生成推荐":
            position = parse_position(values)
            enemy_names = get_en_names_from_selected(window, "-ENEMY-LIST-")
            team_names = get_en_names_from_selected(window, "-TEAM-LIST-")
            ban_names = get_en_names_from_selected(window, "-BAN-LIST-")

            enemy_ids = [en_to_id.get(n, 0) for n in enemy_names if en_to_id.get(n)]
            team_ids = [en_to_id.get(n, 0) for n in team_names if en_to_id.get(n)]
            ban_ids = [en_to_id.get(n, 0) for n in ban_names if en_to_id.get(n)]

            if not enemy_ids:
                window["-STATUS-"].update("请至少添加一个对手英雄")
                continue

            logger.info("生成推荐：位置=%s，对手=%d人，我方=%d人，Ban=%d人",
                        LANE_CN.get(position, position),
                        len(enemy_ids), len(team_ids), len(ban_ids))
            logger.info("对手: %s", ", ".join(enemy_names))
            if team_names:
                logger.info("我方: %s", ", ".join(team_names))
            if ban_names:
                logger.info("Ban: %s", ", ".join(ban_names))

            window["-STATUS-"].update("正在计算推荐...")
            window.refresh()

            # 按需爬取 Counter 数据
            for eid in enemy_ids:
                name = engine._champ_name(eid).lower()
                if name not in counter_cache:
                    logger.info("爬取 %s 的 Counter 数据...", name.capitalize())
                    result = fetcher.get_counter_data(name.capitalize())
                    if result:
                        counter_cache[name] = result
                    # 实时保存缓存
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(counter_cache, f, ensure_ascii=False, indent=2)

            # 调用推荐引擎
            result = engine.recommend(
                candidates=candidates,
                position=position,
                enemy_champs=enemy_ids,
                team_champs=team_ids,
                bans=ban_ids,
                tier_list=tier_list,
                counter_data=counter_cache,
                personal_data={"champions": personal_data} if personal_data else None,
                owned_champs=None,
            )

            # 终端输出 + GUI 弹窗
            print_recommendations(result)
            gui.show_recommendations(result)
            window["-STATUS-"].update("推荐完成！")

        # ── 管理擅长英雄 ──
        if event == "管理擅长英雄":
            gui.show_personal_editor()
            personal_data = _load_personal_champions()
            if personal_data:
                window["-STATUS-"].update(f"已加载 {len(personal_data)} 个擅长英雄")
            else:
                window["-STATUS-"].update("暂无个人数据")

    window.close()


def demo_main():
    """演示模式：使用模拟数据测试推荐和GUI"""
    gui = LolAssistantGUI()
    tray = gui.start_tray()
    fetcher = MetaFetcher()
    engine = RecommendationEngine()

    logger.info("加载版本 Tier 数据...")
    meta_data = fetcher.get_tier_list()
    tier_list = meta_data.get("tier_list", {})
    logger.info("已加载 %d 个位置的 Tier 数据", len(tier_list))

    candidates = [v.get("id") for v in engine._attributes.values() if v.get("id")]
    owned_ids = candidates[:80]

    logger.info("=== 模拟选人场景 ===")
    info = {
        "position": "MID",
        "enemy_champs": [157],
        "team_champs": [64],
        "bans": [11, 42],
    }
    logger.info("你: 中单 | 对手: Yasuo | 我方打野: LeeSin")

    counter_data = {}
    result = fetcher.get_counter_data("Yasuo")
    if result:
        counter_data["yasuo"] = result
        logger.info("已加载 Yasuo 的 Counter 数据 (%d 个克制英雄)",
                    len(result.get("countered_by", [])))

    result = engine.recommend(
        candidates=candidates, position=info["position"],
        enemy_champs=info["enemy_champs"], team_champs=info["team_champs"],
        bans=info["bans"], tier_list=tier_list, counter_data=counter_data,
        personal_data=None, owned_champs=owned_ids,
    )
    print_recommendations(result)
    gui.show_recommendations(result)

    logger.info("演示结束，托盘持续运行中（右键退出）...")
    try:
        while True:
            event = tray.read(timeout=1000)
            if event == "退出":
                break
            if event == "显示仪表盘":
                gui.show_dashboard(None)
    except KeyboardInterrupt:
        logger.info("用户中断")


def lcu_main():
    """LCU模式（需要国际服客户端）"""
    from lcu_connector import LCUConnector
    gui = LolAssistantGUI()
    tray = gui.start_tray()
    connector = LCUConnector()

    logger.info("正在连接 League Client...")
    if not connector.wait_for_client(timeout=60):
        logger.error("无法连接 League Client")
        sys.exit(1)
    logger.info("LCU 连接成功")
    # ... 保持原有LCU流程 ...
    logger.info("LCU模式暂未完整实现，请使用手动模式")


def print_recommendations(result: dict):
    """打印推荐结果到终端"""
    recs = result.get("recommendations", [])
    print("\n" + "=" * 60)
    print(f"  你的位置: {LANE_CN.get(result.get('your_position', '?'), '?')}")
    print(f"  候选英雄: {result.get('total_candidates', 0)} 个")
    print("=" * 60)

    if not recs:
        print("  没有找到推荐英雄")
        return

    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(recs):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        b = r["breakdown"]
        print(f"\n  {medal} {r['champion_name']}  "
              f"推荐度: {r['total_score']:.0f}/100")
        print(f"     ├─ 版本强度: {b['meta_score']:.0f}  "
              f"克制: {b['counter_score']:.0f}  "
              f"个人: {b['personal_score']:.0f}  "
              f"团队: {b['team_score']:.0f}")
        for reason in r.get("reasons", []):
            print(f"     └─ {reason}")
    print()


def download_all():
    """全量数据下载模式：一次性拉取所有英雄数据到本地"""
    import time
    fetcher = MetaFetcher()

    # 1. Tier 列表
    logger.info("=" * 50)
    logger.info("第1步：下载版本 Tier 数据...")
    meta = fetcher.get_tier_list(force_refresh=True)
    tier_list = meta.get("tier_list", {})
    total_heroes = sum(len(v) for v in tier_list.values())
    logger.info("Tier 数据完成：%d 个位置，共 %d 条记录", len(tier_list), total_heroes)

    # 2. Counter 数据 - 全量 172 英雄
    logger.info("=" * 50)
    logger.info("第2步：下载全英雄 Counter 数据 (172个)...")
    all_champion_names = list(CN_DATA.keys())
    logger.info("共 %d 个英雄，5线程并发，预计 1-2 分钟", len(all_champion_names))

    start = time.time()
    fetcher.preload_counters_batch(
        all_champion_names,
        on_progress=lambda done, total, name: print(
            f"\r  [{done:3d}/{total}] {name:20s}", end="", flush=True
        ),
        max_workers=5,
    )
    elapsed = time.time() - start
    print()  # 换行
    logger.info("Counter 数据完成！耗时 %.0f 秒", elapsed)

    # 3. 确认缓存
    cache_file = DATA_DIR / "counter_cache.json"
    with open(cache_file, encoding="utf-8") as f:
        counter_cache = json.load(f)
    logger.info("=" * 50)
    logger.info("下载完成！")
    logger.info("  Tier 数据: %d 个位置", len(tier_list))
    logger.info("  Counter 数据: %d 个英雄", len(counter_cache))
    logger.info("  之后使用 python main.py 启动即可，无需联网")


if __name__ == "__main__":
    init()

    if MODE == "download-all":
        download_all()
    elif MODE == "web":
        from server import start_server
        start_server()
    elif MODE == "demo":
        demo_main()
    elif MODE == "lcu":
        lcu_main()
    elif MODE == "manual":
        manual_main()
    else:
        manual_main()
