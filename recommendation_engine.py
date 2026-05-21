"""推荐引擎 - 四因子加权排序"""

import json
import logging
from pathlib import Path
from typing import Any

from config import (
    DATA_DIR,
    PERSONAL_DEFAULT_SCORE,
    PERSONAL_GAMES_LOW,
    PERSONAL_GAMES_THRESHOLD,
    PERSONAL_NO_DATA_SCORE,
    TEAM_BONUS_AP,
    TEAM_BONUS_CC,
    TEAM_BONUS_TANK,
    TEAM_SCORE_MAX,
    TIER_DEFAULT_SCORE,
    TIER_SCORE,
    WEIGHTS,
)

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """四因子推荐引擎"""

    def __init__(self):
        self._attributes = self._load_attributes()

    # ── 主入口 ────────────────────────────────────────────

    def recommend(
        self,
        *,
        candidates: list[int],              # 候选英雄ID列表
        position: str,                      # 你的位置
        enemy_champs: list[int],            # 对手已选英雄ID
        team_champs: list[int],             # 我方已选英雄ID（不含你）
        bans: list[int],                    # 被Ban英雄ID
        tier_list: dict,                    # 版本Tier数据
        counter_data: dict,                 # Counter数据 {champ_id: {countered_by: [...]}}
        personal_data: dict | None,         # 个人数据
        owned_champs: list[int] | None,     # 拥有的英雄ID
    ) -> dict[str, Any]:
        """执行推荐，返回 Top 3"""
        # 1. 筛选候选池
        pool = self._filter_pool(candidates, bans, team_champs + enemy_champs,
                                 position, owned_champs)

        # 2. 对每个候选计算四维分数
        scored = []
        for champ_id in pool:
            meta_s = self._calc_meta(champ_id, position, tier_list)
            counter_s = self._calc_counter(champ_id, enemy_champs, counter_data)
            personal_s = self._calc_personal(champ_id, personal_data)
            team_s = self._calc_team(champ_id, team_champs)

            total = (
                meta_s * WEIGHTS["meta"]
                + counter_s * WEIGHTS["counter"]
                + personal_s * WEIGHTS["personal"]
                + team_s * WEIGHTS["team"]
            )

            scored.append({
                "champion_id": champ_id,
                "champion_name": self.champ_cn_name(champ_id),
                "total_score": round(total, 1),
                "breakdown": {
                    "meta_score": round(meta_s, 1),
                    "counter_score": round(counter_s, 1),
                    "personal_score": round(personal_s, 1),
                    "team_score": round(team_s, 1),
                },
                "reasons": self._gen_reasons(
                    champ_id, meta_s, counter_s, personal_s, team_s,
                    tier_list, enemy_champs, personal_data,
                ),
            })

        # 3. 排序取 Top 3
        scored.sort(key=lambda x: x["total_score"], reverse=True)

        return {
            "recommendations": scored[:3],
            "your_position": position,
            "total_candidates": len(pool),
        }

    # ── 候选池筛选 ────────────────────────────────────────

    @staticmethod
    def _filter_pool(
        candidates: list[int],
        bans: list[int],
        picked: list[int],
        position: str,
        owned: list[int] | None,
    ) -> list[int]:
        pool = set(candidates)
        # 排除被Ban
        pool -= set(bans)
        # 排除已被选的
        pool -= set(picked)
        if owned:
            pool &= set(owned)
        if not pool:
            # 极端情况：候选池为空，返回全部候选（除被ban和被选）
            pool = set(candidates) - set(bans) - set(picked)
        return sorted(pool)

    # ── 四维分数 ──────────────────────────────────────────

    def _calc_meta(self, champ_id: int, position: str,
                   tier_list: dict) -> float:
        """版本强度分 (权重40%)"""
        champ_name = self._champ_name(champ_id).lower()
        pos_data = tier_list.get(position, [])
        for entry in pos_data:
            if entry.get("name", "").lower() == champ_name:
                tier = str(entry.get("tier", ""))
                return TIER_SCORE.get(tier, TIER_DEFAULT_SCORE)
        return TIER_DEFAULT_SCORE

    def _calc_counter(self, champ_id: int, enemy_champs: list[int],
                      counter_data: dict) -> float:
        """克制分 (权重30%)"""
        if not enemy_champs:
            return 50.0
        champ_name = self._champ_name(champ_id).lower()
        scores = []
        for eid in enemy_champs:
            e_name = self._champ_name(eid).lower()
            entry = counter_data.get(e_name, {})
            countered_by = entry.get("countered_by", []) if isinstance(entry, dict) else []
            for c in countered_by:
                if c.get("name", "").lower() == champ_name:
                    wr = c.get("winRateAgainst")
                    if wr is not None:
                        score = min(100, max(0, (float(wr) - 45) * 2))
                        scores.append(score)
        if not scores:
            return 50.0
        return sum(scores) / len(scores)

    @staticmethod
    def _calc_personal(champ_id: int,
                       personal_data: dict | None) -> float:
        """个人擅长分 (权重20%)"""
        if not personal_data:
            return PERSONAL_NO_DATA_SCORE
        champions = personal_data.get("champions", []) if isinstance(personal_data, dict) else []
        for c in champions:
            if c.get("id") == champ_id:
                games = c.get("gamesPlayed", 0)
                wr = c.get("winRate", 50)
                if games >= PERSONAL_GAMES_THRESHOLD:
                    return float(wr)
                if games >= PERSONAL_GAMES_LOW:
                    return float(wr) * (games / PERSONAL_GAMES_THRESHOLD)
                return PERSONAL_DEFAULT_SCORE
        return PERSONAL_DEFAULT_SCORE

    def _calc_team(self, champ_id: int, team_champs: list[int]) -> float:
        """团队适配分 (权重10%)"""
        score = 0.0
        my_attr = self._attributes.get(str(champ_id), {})

        # 检查队伍缺什么
        has_ap = False
        has_tank = False
        has_cc = False
        for tid in team_champs:
            attr = self._attributes.get(str(tid), {})
            if attr.get("damageType") == "AP":
                has_ap = True
            if attr.get("role") == "TANK" or attr.get("damageType") == "TANK":
                has_tank = True
            if attr.get("hasHardCC"):
                has_cc = True

        # 缺AP伤害 → 补AP英雄加分
        if not has_ap and my_attr.get("damageType") == "AP":
            score += TEAM_BONUS_AP
        # 缺前排坦克 → 坦克英雄加分
        if not has_tank and my_attr.get("role") in ("TANK", "FIGHTER"):
            score += TEAM_BONUS_TANK
        # 缺控制 → 控制型英雄加分
        if not has_cc and my_attr.get("hasHardCC"):
            score += TEAM_BONUS_CC

        return min(score, float(TEAM_SCORE_MAX))

    # ── 理由生成 ──────────────────────────────────────────

    def _gen_reasons(self, champ_id: int, meta_s: float,
                     counter_s: float, personal_s: float,
                     team_s: float, tier_list: dict,
                     enemy_champs: list[int],
                     personal_data: dict | None) -> list[str]:
        reasons = []

        # 版本
        meta_entry = None
        champ_name = self._champ_name(champ_id).lower()
        for pos_data in tier_list.values():
            for e in pos_data:
                if e.get("name", "").lower() == champ_name:
                    meta_entry = e
                    break
        if meta_entry:
            tier = meta_entry.get("tier", "")
            wr = meta_entry.get("winRate")
            if tier and wr:
                reasons.append(f"版本{tier}（胜率{wr}%）")
            elif tier:
                reasons.append(f"版本{tier}")
            elif wr:
                reasons.append(f"版本胜率{wr}%")

        # 克制
        if counter_s >= 80:
            reasons.append("强力克制对手英雄")
        elif counter_s >= 60:
            reasons.append("对位有优势")

        # 个人
        if personal_data:
            for c in personal_data.get("champions", []):
                if c.get("id") == champ_id:
                    games = c.get("gamesPlayed", 0)
                    wr = c.get("winRate", 0)
                    if games >= PERSONAL_GAMES_THRESHOLD:
                        reasons.append(f"擅长英雄（{games}场，胜率{wr}%）")
                    elif games > 0:
                        reasons.append(f"有使用经验（{games}场，胜率{wr}%）")
                    break

        # 团队
        if team_s >= 20:
            my_attr = self._attributes.get(str(champ_id), {})
            if my_attr.get("damageType") == "AP":
                reasons.append("补充团队AP伤害")
            if my_attr.get("role") in ("TANK", "FIGHTER"):
                reasons.append("补充前排坦度")

        return reasons

    # ── 工具 ──────────────────────────────────────────────

    def _champ_name(self, champ_id: int) -> str:
        """获取英雄英文名"""
        for attr in self._attributes.values():
            if attr.get("id") == champ_id:
                return attr.get("name", str(champ_id))
        return str(champ_id)

    def champ_cn_name(self, champ_id: int) -> str:
        """获取英雄中文名（优先用国服名称，回退到英文名）"""
        en_name = self._champ_name(champ_id)
        if en_name and en_name[0].isdigit():
            return en_name
        try:
            with open(DATA_DIR / "champion_names_cn.json", encoding="utf-8") as f:
                cn_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return en_name
        # 大小写不敏感匹配
        for key, info in cn_data.items():
            if key.lower() == en_name.lower():
                if isinstance(info, dict):
                    return info.get("name_cn", en_name)
                return en_name
        return en_name

    @staticmethod
    def _load_attributes() -> dict[str, Any]:
        path = DATA_DIR / "champion_attributes.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        logger.warning("champion_attributes.json 未找到，团队适配分将不准确")
        return {}
