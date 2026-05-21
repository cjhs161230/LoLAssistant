"""GUI 模块 — 现代暗黑风格界面"""

import json
import logging
from pathlib import Path
from typing import Any

import PySimpleGUI as sg

from config import DATA_DIR

logger = logging.getLogger(__name__)

# ═══ 配色方案 ═══════════════════════════════════════
C_BG         = "#0D1117"   # 主背景
C_SURFACE    = "#161B22"   # 卡片/列表背景
C_BORDER     = "#30363D"   # 边框
C_TEXT       = "#E6EDF3"   # 主文字
C_SUBTEXT    = "#8B949E"   # 次要文字
C_ACCENT     = "#C8AA6E"   # 强调色（LoL 金）
C_ACCENT2    = "#58A6FF"   # 蓝色强调
C_SUCCESS    = "#3FB950"   # 成功
C_WARN       = "#D29922"   # 警告
C_DANGER     = "#F85149"   # 危险
C_BTN_PRIMARY = (C_BG, C_ACCENT)      # 主按钮 (文字色, 背景色)
C_BTN_NORMAL  = (C_TEXT, C_SURFACE)   # 普通按钮
C_INPUT_BG    = "#0D1117"   # 输入框背景
C_LIST_SEL    = (C_TEXT, "#1F2937")   # 列表选中

# ═══ 字体 ═══════════════════════════════════════════
FONT_TITLE   = ("Microsoft YaHei", 16, "bold")
FONT_HEADING = ("Microsoft YaHei", 12, "bold")
FONT_BODY    = ("Microsoft YaHei", 11)
FONT_SMALL   = ("Microsoft YaHei", 10)
FONT_MONO    = ("Cascadia Code", 10)

# ═══ 全局设置 ═══════════════════════════════════════
sg.set_options(
    font=FONT_BODY,
    background_color=C_BG,
    text_color=C_TEXT,
    input_text_color=C_TEXT,
    input_elements_background_color=C_INPUT_BG,
    button_color=C_BTN_NORMAL,
    border_width=0,
    element_padding=(8, 6),
)
sg.theme_background_color(C_BG)
sg.theme_text_color(C_TEXT)
sg.theme_button_color(C_BTN_NORMAL)

DEFAULT_BUTTON = {"size": (12, 1), "font": FONT_BODY}
PRIMARY_BUTTON = {"size": (14, 1), "font": FONT_BODY,
                  "button_color": C_BTN_PRIMARY}

LANE_CN = {"TOP": "上单", "JUNGLE": "打野", "MID": "中单",
           "BOTTOM": "ADC", "UTILITY": "辅助"}


# ═══ 数据加载 ═══════════════════════════════════════

def _load_cn_data() -> dict[str, dict]:
    for name in ("champion_names_cn.json", "champion_attributes.json"):
        path = DATA_DIR / name
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
    return {}


def _build_display_list(cn_data: dict) -> list[str]:
    result = []
    for en_name, info in cn_data.items():
        cn = info.get("name_cn", en_name) if isinstance(info, dict) else en_name
        result.append(f"{cn}  {en_name}")
    result.sort(key=lambda x: x.split()[0])
    return result


def _match_hero(query: str, display_name: str, cn_data: dict) -> bool:
    if not query.strip():
        return True
    q = query.strip().lower()
    parts = display_name.rsplit("  ", 1)
    en_name = parts[-1] if len(parts) == 2 else ""
    cn_display = parts[0] if len(parts) == 2 else display_name
    if q in cn_display.lower() or q in en_name.lower():
        return True
    if en_name and en_name in cn_data:
        info = cn_data[en_name]
        if isinstance(info, dict):
            for term in info.get("search_terms", []):
                if q in term.lower():
                    return True
    return False


CN_DATA = _load_cn_data()
DISPLAY_LIST = _build_display_list(CN_DATA)


# ═══ 通用组件 ═══════════════════════════════════════

def _section(title: str) -> list:
    """生成带标题的分隔区"""
    return [sg.Text(title, font=FONT_HEADING, text_color=C_SUBTEXT,
                    pad=(8, (12, 4)))]


def _sep() -> list:
    return [sg.HorizontalSeparator(color=C_BORDER, pad=(0, 4))]


def _listbox(key: str, size: tuple = (24, 8), values: list = None) -> sg.Listbox:
    return sg.Listbox(
        values=values or [], key=key, size=size, font=FONT_SMALL,
        select_mode=sg.LISTBOX_SELECT_MODE_SINGLE, enable_events=True,
        background_color=C_SURFACE, text_color=C_TEXT,
        sbar_background_color=C_BG, sbar_arrow_color=C_ACCENT,
        no_scrollbar=False,
    )


# ═══ 主界面类 ═══════════════════════════════════════

class LolAssistantGUI:
    """选人助手 GUI"""

    def __init__(self):
        self._tray = None

    # ── 系统托盘 ──────────────────────────────────

    def start_tray(self) -> sg.SystemTray:
        menu = ["", ["显示仪表盘", "---", "退出"]]
        self._tray = sg.SystemTray(
            menu=menu,
            filename=DATA_DIR / "icon.png" if (DATA_DIR / "icon.png").exists() else None,
            data_base64=self._default_icon(),
            tooltip="LoL 选人助手",
        )
        return self._tray

    @staticmethod
    def _default_icon() -> bytes:
        import base64
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbHYQAAAABJRU5ErkJggg=="
        )

    # ── 推荐弹窗 ──────────────────────────────────

    def show_recommendations(self, result: dict):
        recs = result.get("recommendations", [])
        position = result.get("your_position", "?")

        layout = [
            [sg.Text("推荐结果", font=FONT_TITLE, text_color=C_ACCENT)],
            [sg.Text(f"你的位置：{LANE_CN.get(position, position)}",
                    font=FONT_BODY, text_color=C_SUBTEXT)],
            [_sep()[0]],
        ]

        medals = ["1", "2", "3"]
        for i, r in enumerate(recs[:3]):
            b = r["breakdown"]
            reasons = r.get("reasons", [])
            reasons_text = "  ·  ".join(reasons) if reasons else "暂无推荐理由"
            score = r["total_score"]
            bar = _score_bar(score)

            card = [
                [sg.Text(f"{medals[i]}. {r['champion_name']}", font=FONT_HEADING,
                        text_color=C_TEXT),
                 sg.Push(),
                 sg.Text(f"{score:.0f} 分", font=FONT_HEADING,
                        text_color=C_ACCENT)],
                [sg.Text(bar, font=FONT_MONO, text_color=_score_color(score))],
                [sg.Text(f"版本 {b['meta_score']:.0f}  ·  "
                         f"克制 {b['counter_score']:.0f}  ·  "
                         f"个人 {b['personal_score']:.0f}  ·  "
                         f"团队 {b['team_score']:.0f}",
                         font=FONT_SMALL, text_color=C_SUBTEXT)],
                [sg.Text(reasons_text, font=FONT_SMALL, text_color=C_ACCENT2)],
            ]
            layout.append([sg.Frame("", card, pad=(0, 6),
                                    background_color=C_SURFACE,
                                    border_width=0, relief=sg.RELIEF_FLAT)])

        layout.extend([
            [_sep()[0]],
            [sg.Button("关闭", **PRIMARY_BUTTON),
             sg.Push(),
             sg.Button("仪表盘", **DEFAULT_BUTTON)],
        ])

        window = sg.Window("LoL 选人助手", layout, keep_on_top=True, finalize=True,
                          background_color=C_BG, margins=(16, 12))
        while True:
            event, _ = window.read()
            if event in (sg.WIN_CLOSED, "关闭"):
                break
            if event == "仪表盘":
                window.hide()
                self.show_dashboard(None)
                window.un_hide()
        window.close()

    # ── 仪表盘 ────────────────────────────────────

    def show_dashboard(self, personal_data: dict | None = None):
        layout = [
            [sg.Text("个人数据", font=FONT_TITLE, text_color=C_ACCENT)],
            [_sep()[0]],
        ]
        if personal_data:
            champions = personal_data.get("champions", [])
            if champions:
                data_rows = []
                for c in sorted(champions,
                                key=lambda x: x.get("gamesPlayed", 0),
                                reverse=True)[:15]:
                    data_rows.append([
                        c.get("name", "?"),
                        str(c.get("gamesPlayed", 0)),
                        f"{c.get('winRate', 0)}%",
                        f"{c.get('kda', '-')}",
                    ])
                layout.append([sg.Table(
                    values=data_rows,
                    headings=["英雄", "场次", "胜率", "KDA"],
                    auto_size_columns=True, justification="center",
                    num_rows=min(len(data_rows), 15), font=FONT_BODY,
                    background_color=C_SURFACE, text_color=C_TEXT,
                    header_background_color=C_BG,
                    header_text_color=C_SUBTEXT,
                    selected_row_colors=C_LIST_SEL,
                )])
            else:
                layout.append([sg.Text("暂无数据", font=FONT_BODY,
                                      text_color=C_SUBTEXT)])
        else:
            layout.append([sg.Text("未加载个人数据", font=FONT_BODY,
                                  text_color=C_SUBTEXT)])
        layout.extend([
            [_sep()[0]],
            [sg.Push(), sg.Button("关闭", **PRIMARY_BUTTON)],
        ])
        sg.Window("个人数据", layout, font=FONT_BODY, finalize=True,
                 background_color=C_BG, margins=(16, 12)).read(close=True)

    # ── 手动模式主窗口 ────────────────────────────

    def show_manual_mode(self) -> sg.Window:
        """显示手动选人主窗口"""

        list_size = (26, 6)

        # --- 左侧：搜索 ---
        left = [
            [sg.Text("搜索英雄", font=FONT_HEADING, text_color=C_SUBTEXT)],
            [sg.Text("支持中文、英文、外号", font=FONT_SMALL, text_color=C_BORDER)],
            [sg.Input(key="-SEARCH-", enable_events=True, size=(28, 1),
                     font=FONT_BODY, background_color=C_SURFACE,
                     text_color=C_TEXT, border_width=1)],
            [_listbox("-HERO-LIST-", size=(28, 14))],
        ]

        # --- 右侧：添加按钮 ---
        btn_add = {"size": (12, 1), "font": FONT_SMALL,
                   "button_color": (C_ACCENT2, C_SURFACE)}
        right = [
            [sg.Text("")],
            [sg.Button("添加到对手", key="-ADD-ENEMY-", **btn_add),
             sg.Text("0/5", key="-CNT-ENEMY-", font=FONT_SMALL,
                    text_color=C_SUBTEXT)],
            [sg.Button("添加到我方", key="-ADD-TEAM-", **btn_add),
             sg.Text("0/4", key="-CNT-TEAM-", font=FONT_SMALL,
                    text_color=C_SUBTEXT)],
            [sg.Button("添加到 Ban", key="-ADD-BAN-", **btn_add),
             sg.Text("0/10", key="-CNT-BAN-", font=FONT_SMALL,
                    text_color=C_SUBTEXT)],
        ]

        # --- 已选列表 ---
        def _selected_section(title: str, list_key: str, rm_key: str,
                              clr_key: str) -> sg.Column:
            return sg.Column([
                [sg.Text(title, font=FONT_HEADING, text_color=C_TEXT)],
                [_listbox(list_key, size=list_size)],
                [sg.Button("移除", key=rm_key, size=(6, 1), font=FONT_SMALL,
                          button_color=(C_DANGER, C_SURFACE)),
                 sg.Button("清空", key=clr_key, size=(6, 1), font=FONT_SMALL)],
            ], element_justification="center", vertical_alignment="top",
               background_color=C_BG)

        layout = [
            # 标题
            [sg.Text("LoL 选人助手", font=FONT_TITLE, text_color=C_ACCENT),
             sg.Text("v1.0", font=FONT_SMALL, text_color=C_BORDER, pad=(6, 8)),
             sg.Push(),
             sg.Text("手动模式", font=FONT_SMALL, text_color=C_SUBTEXT)],

            [_sep()[0]],

            # 位置选择
            [_section("你的位置")],
            [sg.Radio("上单", "pos", key="-POS-TOP-", font=FONT_BODY,
                     background_color=C_BG, text_color=C_TEXT,
                     circle_color=C_BORDER, size=(5, 1)),
             sg.Radio("打野", "pos", key="-POS-JUNGLE-", font=FONT_BODY,
                     background_color=C_BG, text_color=C_TEXT,
                     circle_color=C_BORDER, size=(5, 1)),
             sg.Radio("中单", "pos", key="-POS-MID-", default=True, font=FONT_BODY,
                     background_color=C_BG, text_color=C_TEXT,
                     circle_color=C_ACCENT2, size=(5, 1)),
             sg.Radio("ADC", "pos", key="-POS-BOTTOM-", font=FONT_BODY,
                     background_color=C_BG, text_color=C_TEXT,
                     circle_color=C_BORDER, size=(5, 1)),
             sg.Radio("辅助", "pos", key="-POS-UTILITY-", font=FONT_BODY,
                     background_color=C_BG, text_color=C_TEXT,
                     circle_color=C_BORDER, size=(5, 1))],

            [_sep()[0]],

            # 主体区域
            [sg.Column(left, vertical_alignment="top", background_color=C_BG),
             sg.Column(right, vertical_alignment="top", background_color=C_BG,
                      element_justification="center")],

            [_sep()[0]],

            # 已选英雄
            [_selected_section("对手已选 (0/5)", "-ENEMY-LIST-",
                               "-RM-ENEMY-", "-CLR-ENEMY-"),
             _selected_section("我方已选 (0/4)", "-TEAM-LIST-",
                               "-RM-TEAM-", "-CLR-TEAM-"),
             _selected_section("Ban 位 (0/10)", "-BAN-LIST-",
                               "-RM-BAN-", "-CLR-BAN-")],

            [_sep()[0]],

            # 状态栏
            [sg.Text("", key="-STATUS-", font=FONT_SMALL, text_color=C_ACCENT2,
                    size=(35, 1)),
             sg.Push(),
             sg.Button("管理擅长英雄", size=(14, 1), font=FONT_SMALL),
             sg.Button("生成推荐", **PRIMARY_BUTTON)],
        ]

        window = sg.Window("LoL 智能选人助手", layout, finalize=True,
                          background_color=C_BG, margins=(16, 12),
                          resizable=True)
        return window

    # ── 个人英雄编辑器 ────────────────────────────

    def show_personal_editor(self):
        """管理擅长英雄"""
        save_path = DATA_DIR / "personal_champions.json"
        champions = []
        if save_path.exists():
            try:
                with open(save_path, encoding="utf-8") as f:
                    champions = json.load(f).get("champions", [])
            except (json.JSONDecodeError, OSError):
                pass

        en_to_cn = {}
        for en_name, info in CN_DATA.items():
            if isinstance(info, dict):
                en_to_cn[en_name] = info.get("name_cn", en_name)

        input_size = (8, 1)
        search = [
            [sg.Text("搜索英雄", font=FONT_HEADING, text_color=C_SUBTEXT)],
            [sg.Input(key="-PE-SEARCH-", enable_events=True, size=(22, 1),
                     background_color=C_SURFACE, text_color=C_TEXT)],
            [_listbox("-PE-LIST-", size=(22, 10))],
        ]

        form = [
            [sg.Text("场次", font=FONT_SMALL, text_color=C_SUBTEXT),
             sg.Input(key="-PE-GAMES-", size=input_size, default_text="0",
                     background_color=C_SURFACE, text_color=C_TEXT)],
            [sg.Text("胜场", font=FONT_SMALL, text_color=C_SUBTEXT),
             sg.Input(key="-PE-WINS-", size=input_size, default_text="0",
                     background_color=C_SURFACE, text_color=C_TEXT)],
            [sg.Text("胜率", font=FONT_SMALL, text_color=C_SUBTEXT),
             sg.Text("—", key="-PE-WR-", font=FONT_HEADING, text_color=C_ACCENT)],
            [sg.Button("添加 / 更新", key="-PE-ADD-", size=(12, 1),
                      font=FONT_SMALL, button_color=(C_SUCCESS, C_SURFACE))],
            [_sep()[0]],
            [sg.Text("已录入", font=FONT_SMALL, text_color=C_SUBTEXT)],
            [_listbox("-PE-SAVED-", size=(22, 7))],
            [sg.Button("移除选中", key="-PE-DEL-", size=(8, 1), font=FONT_SMALL,
                      button_color=(C_DANGER, C_SURFACE)),
             sg.Button("清空", key="-PE-CLR-", size=(6, 1), font=FONT_SMALL)],
        ]

        layout = [
            [sg.Text("管理擅长英雄", font=FONT_TITLE, text_color=C_ACCENT)],
            [sg.Text("录入数据后，推荐引擎会参考个人擅长分",
                    font=FONT_SMALL, text_color=C_SUBTEXT)],
            [_sep()[0]],
            [sg.Column(search, vertical_alignment="top", background_color=C_BG),
             sg.Column(form, vertical_alignment="top", background_color=C_BG)],
            [_sep()[0]],
            [sg.Text("", key="-PE-STATUS-", font=FONT_SMALL, text_color=C_ACCENT2,
                    size=(30, 1)),
             sg.Push(),
             sg.Button("保存并关闭", key="-PE-SAVE-", **PRIMARY_BUTTON)],
        ]

        window = sg.Window("擅长英雄管理", layout, finalize=True,
                          background_color=C_BG, margins=(16, 12))

        def _refresh():
            items = []
            for c in champions:
                en = c.get("name", "")
                cn = en_to_cn.get(en, en)
                g = c.get("gamesPlayed", 0)
                wr = c.get("winRate", 0)
                items.append(f"{cn}    {g}场    胜率{wr}%")
            window["-PE-SAVED-"].update(values=items)

        _refresh()

        while True:
            event, values = window.read()

            if event in (sg.WIN_CLOSED, "-PE-SAVE-"):
                break

            if event == "-PE-SEARCH-":
                update_hero_list(window, "-PE-LIST-", values["-PE-SEARCH-"])

            if event in ("-PE-GAMES-", "-PE-WINS-"):
                try:
                    g = int(values["-PE-GAMES-"] or 0)
                    w = int(values["-PE-WINS-"] or 0)
                    if g > 0 and w <= g:
                        window["-PE-WR-"].update(f"{round(w/g*100, 1)}%")
                    else:
                        window["-PE-WR-"].update("—")
                except ValueError:
                    window["-PE-WR-"].update("—")

            if event == "-PE-ADD-":
                sel = values.get("-PE-LIST-")
                if not sel:
                    window["-PE-STATUS-"].update("请先选择英雄")
                    continue
                en = get_en_name(sel[0])
                try:
                    g = int(values["-PE-GAMES-"] or 0)
                    w = int(values["-PE-WINS-"] or 0)
                except ValueError:
                    window["-PE-STATUS-"].update("数字格式错误")
                    continue
                if g <= 0:
                    window["-PE-STATUS-"].update("场次必须 > 0")
                    continue
                if w > g:
                    window["-PE-STATUS-"].update("胜场不能 > 场次")
                    continue
                wr = round(w / g * 100, 1)

                found = False
                for c in champions:
                    if c.get("name") == en:
                        c.update(gamesPlayed=g, wins=w, winRate=wr)
                        found = True
                        break
                if not found:
                    eid = 0
                    for enk, info in CN_DATA.items():
                        if isinstance(info, dict) and enk == en:
                            eid = info.get("id", 0)
                            break
                    champions.append({"id": eid, "name": en,
                                     "gamesPlayed": g, "wins": w, "winRate": wr})

                _refresh()
                window["-PE-STATUS-"].update(
                    f"已录入 {get_cn_name(sel[0])} ({g}场 {wr}%)")

            if event == "-PE-DEL-":
                s = values.get("-PE-SAVED-")
                if s:
                    name_part = s[0].split("    ")[0].strip()
                    en_del = None
                    for c in champions:
                        if en_to_cn.get(c.get("name", ""), "") == name_part:
                            en_del = c.get("name")
                            break
                    if en_del:
                        champions[:] = [c for c in champions
                                       if c.get("name") != en_del]
                        _refresh()
                        window["-PE-STATUS-"].update("已移除")

            if event == "-PE-CLR-":
                champions.clear()
                _refresh()
                window["-PE-STATUS-"].update("已清空")

        # 保存
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump({"champions": champions}, f, ensure_ascii=False, indent=2)

        window.close()


# ═══ 工具函数 ═══════════════════════════════════════

def get_en_name(display_name: str) -> str:
    parts = display_name.rsplit("  ", 1)
    return parts[-1] if len(parts) == 2 else display_name


def get_cn_name(display_name: str) -> str:
    parts = display_name.rsplit("  ", 1)
    return parts[0] if len(parts) == 2 else display_name


def update_hero_list(window: sg.Window, key: str, query: str):
    filtered = [d for d in DISPLAY_LIST if _match_hero(query, d, CN_DATA)]
    window[key].update(values=filtered)


def add_to_list(window: sg.Window, list_key: str, hero_name: str,
                max_count: int) -> bool:
    current = window[list_key].get_list_values()
    if len(current) >= max_count:
        window["-STATUS-"].update(f"已满（最多 {max_count} 个）")
        return False
    if hero_name in current:
        window["-STATUS-"].update(f"「{hero_name}」已在列表中")
        return False
    current.append(hero_name)
    window[list_key].update(values=current)
    _update_counts(window)
    window["-STATUS-"].update(f"已添加「{hero_name}」")
    return True


def remove_from_list(window: sg.Window, list_key: str):
    sel = window[list_key].get()
    if sel:
        cur = window[list_key].get_list_values()
        cur.remove(sel[0])
        window[list_key].update(values=cur)
        _update_counts(window)


def clear_list(window: sg.Window, list_key: str):
    window[list_key].update(values=[])
    _update_counts(window)


def _update_counts(window: sg.Window):
    for key, label, max_n in [("-ENEMY-LIST-", "-CNT-ENEMY-", 5),
                                ("-TEAM-LIST-", "-CNT-TEAM-", 4),
                                ("-BAN-LIST-", "-CNT-BAN-", 10)]:
        n = len(window[key].get_list_values())
        window[label].update(f"{n}/{max_n}")


def get_en_names_from_selected(window: sg.Window, list_key: str) -> list[str]:
    return [get_en_name(n) for n in window[list_key].get_list_values()]


def _score_bar(score: float) -> str:
    """视觉化分数条"""
    n = int(score / 10)
    return "█" * n + "░" * (10 - n)


def _score_color(score: float) -> str:
    if score >= 80:   return C_SUCCESS
    if score >= 60:   return C_ACCENT
    if score >= 40:   return C_WARN
    return C_DANGER
