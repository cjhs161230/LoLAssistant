"""Meta 数据采集模块 - 通过 OP.GG MCP API 获取英雄数据"""

import concurrent.futures
import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from config import CACHE_TTL_HOURS, DATA_DIR

logger = logging.getLogger(__name__)

MCP_URL = "https://mcp-api.op.gg/mcp"

# 位置名称映射
LANE_MAP = {"top": "TOP", "mid": "MID", "jungle": "JUNGLE",
            "adc": "BOTTOM", "support": "UTILITY"}


class MetaFetcher:
    """版本数据和 Counter 关系采集器，通过 OP.GG MCP API 获取"""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "LoLAssistant/1.0",
        })
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── 公开接口 ──────────────────────────────────────────

    def get_tier_list(self, force_refresh: bool = False) -> dict:
        """获取各位置 Tier 列表"""
        cache_file = DATA_DIR / "meta_cache.json"
        if not force_refresh:
            cached = self._load_cache(cache_file)
            if cached:
                return cached

        logger.info("拉取 OP.GG 国服英雄排行数据...")
        data = self._fetch_all_tiers()
        if data:
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._save_cache(cache_file, data)
            return data
        cached = self._load_cache(cache_file, ignore_ttl=True)
        if cached:
            logger.warning("API 请求失败，使用旧缓存")
            return cached
        return {"tier_list": {}, "last_updated": None}

    def get_counter_data(self, champion_name: str,
                         force_refresh: bool = False) -> dict:
        """获取某英雄的 Counter 关系"""
        cache_file = DATA_DIR / "counter_cache.json"
        all_counters = self._load_raw_cache(cache_file)

        key = champion_name.lower()
        if not force_refresh and key in all_counters:
            return all_counters[key]

        logger.info("拉取 %s 的 Counter 数据...", champion_name)
        data = self._fetch_counters(champion_name)
        if data:
            all_counters[key] = {"name": champion_name, "countered_by": data}
            self._save_cache(cache_file, all_counters)
            return all_counters[key]
        return {"name": champion_name, "countered_by": []}

    def get_summoner_champions(self, game_name: str, tag_line: str,
                              region: str = "cn") -> list[dict] | None:
        """查询召唤师个人英雄数据（胜率/场次/KDA）"""
        logger.info("查询召唤师 %s#%s 的个人数据...", game_name, tag_line)
        text = self._mcp_call("lol_get_summoner_profile", {
            "game_name": game_name,
            "tag_line": tag_line,
            "region": region,
            "desired_output_fields": [
                "data.summoner.most_champions.champion_stats.{champion_name,id,play,win,lose,assist,death,kill}",
                "data.summoner.most_champions.{game_type,lose,play,win}",
            ],
        })
        if not text:
            return None
        return self._parse_summoner_stats(text)

    def preload_counters_batch(
        self,
        champion_names: list[str],
        on_progress: callable = None,
        max_workers: int = 5,
    ) -> dict:
        """并发预加载一批英雄的 Counter 数据，返回完整 counter_cache

        Args:
            champion_names: 英雄英文名列表
            on_progress: 进度回调 (done, total, name) -> None
            max_workers: 并发线程数
        """
        cache_file = DATA_DIR / "counter_cache.json"
        all_counters = self._load_raw_cache(cache_file)
        total = len(champion_names)
        done_count = [0]  # 用列表以便在线程中修改
        lock = threading.Lock()

        names_to_fetch = []
        for name in champion_names:
            key = name.lower()
            if key not in all_counters:
                names_to_fetch.append(name)

        if not names_to_fetch:
            logger.info("Counter 数据已全部缓存，跳过预加载")
            if on_progress:
                on_progress(total, total, "")
            return all_counters

        logger.info("开始预加载 %d/%d 个英雄的 Counter 数据 (%d线程并发)...",
                    len(names_to_fetch), total, max_workers)

        def fetch_one(name: str) -> tuple[str, dict]:
            data = self._fetch_counters(name)
            return name, {"name": name, "countered_by": data}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(fetch_one, name) for name in names_to_fetch]
            for future in concurrent.futures.as_completed(futures):
                try:
                    name, result = future.result()
                    with lock:
                        all_counters[name.lower()] = result
                        done_count[0] += 1
                        # 定期保存缓存
                        if done_count[0] % 5 == 0:
                            self._save_cache(cache_file, all_counters)
                        if on_progress:
                            on_progress(done_count[0], total, name)
                except Exception as e:
                    logger.warning("预加载 %s 失败: %s", name, e)
                    with lock:
                        done_count[0] += 1

        # 最终保存
        self._save_cache(cache_file, all_counters)
        logger.info("Counter 预加载完成 (%d 个英雄)", len(all_counters))
        return all_counters

    # ── 召唤师数据解析 ────────────────────────────────────

    @staticmethod
    def _parse_summoner_stats(text: str) -> list[dict] | None:
        """从 MCP 返回文本中解析召唤师英雄数据"""
        results: list[dict] = []
        # 匹配模式: ChampionStat(123,"Annie",45,30,15,...)
        for m in re.finditer(
            r'ChampionStat\((\d+),\s*"(\w+)",(\d+),(\d+),(\d+)',
            text,
        ):
            champ_id = int(m.group(1))
            name = m.group(2)
            play = int(m.group(3))
            win = int(m.group(4))
            lose = int(m.group(5))
            if play > 0:
                results.append({
                    "id": champ_id,
                    "name": name,
                    "gamesPlayed": play,
                    "wins": win,
                    "losses": lose,
                    "winRate": round(win / play * 100, 1),
                })

        if results:
            logger.info("解析到 %d 个英雄的个人数据", len(results))
            return results
        return None

    # ── MCP API 调用 ──────────────────────────────────────

    def _mcp_call(self, tool: str, args: dict) -> Any | None:
        """调用 OP.GG MCP 的 JSON-RPC 端点"""
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }
        try:
            resp = self._session.post(MCP_URL, json=payload, timeout=20)
            if resp.status_code != 200:
                logger.warning("MCP API %s → %s", tool, resp.status_code)
                return None
            data = resp.json()
            if "error" in data:
                logger.warning("MCP %s 返回错误: %s", tool, data["error"].get("message", ""))
                return None
            for item in data.get("result", {}).get("content", []):
                if item.get("type") == "text":
                    return item["text"]
            return None
        except Exception as e:
            logger.error("MCP 请求失败 %s: %s", tool, e)
            return None

    # ── 数据获取 ──────────────────────────────────────────

    def _fetch_all_tiers(self) -> dict | None:
        """获取所有位置的 Tier 列表"""
        text = self._mcp_call("lol_list_lane_meta_champions",
                              {"lane": "all", "region": "cn"})
        if not text:
            return None
        return self._parse_tier_text(text)

    def _fetch_counters(self, champion_name: str) -> list[dict]:
        """获取英雄的 Counter 数据"""
        text = self._mcp_call("lol_get_champion_analysis", {
            "game_mode": "RANKED",
            "champion": champion_name,
            "position": "mid",
            "region": "cn",
        })
        if not text:
            return []
        return self._parse_counter_text(text)

    # ── 文本解析 ──────────────────────────────────────────

    def _parse_tier_text(self, text: str) -> dict:
        """解析 MCP 返回的 Champion 文本格式，结合属性表按位置分组"""
        tier_list: dict[str, list[dict]] = {}

        records = self._parse_top_calls(text)
        if not records:
            logger.warning("未能解析 Tier 数据，格式可能已变化")
            return {"tier_list": {}, "patch": ""}

        # 加载英雄属性表，获取位置映射
        name_to_positions = self._load_name_positions()

        for name, win_rate, tier in records:
            positions = name_to_positions.get(name.lower(), ["MID"])
            for pos in positions:
                tier_list.setdefault(pos, []).append({
                    "name": name,
                    "winRate": win_rate,
                    "tier": str(tier),
                })

        return {"tier_list": tier_list, "patch": ""}

    @staticmethod
    def _parse_top_calls(text: str) -> list[tuple[str, float, int]]:
        """解析 Top() 函数调用，返回 [(name, win_rate, tier), ...]"""
        results = []
        for m in re.finditer(r'Top\(([^)]+)\)', text):
            args = m.group(1)
            parts = []
            current = ""
            in_str = False
            for ch in args:
                if ch == '"':
                    in_str = not in_str
                    current += ch
                elif ch == "," and not in_str:
                    parts.append(current)
                    current = ""
                else:
                    current += ch
            parts.append(current)

            if len(parts) >= 11:
                name = parts[0].strip('"')
                try:
                    win_rate = round(float(parts[5]) * 100, 1)
                except (ValueError, IndexError):
                    win_rate = 0.0
                tier_str = parts[10].strip()
                if tier_str not in ("null", ""):
                    try:
                        results.append((name, win_rate, int(tier_str)))
                    except ValueError:
                        pass
        return results

    @staticmethod
    def _load_name_positions() -> dict[str, list[str]]:
        """加载英雄属性表，返回 name->positions 映射"""
        path = DATA_DIR / "champion_attributes.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                attrs = json.load(f)
            return {
                v.get("name", "").lower(): v.get("positions", ["MID"])
                for v in attrs.values()
            }
        except (json.JSONDecodeError, OSError):
            return {}

    def _parse_counter_text(self, text: str) -> list[dict]:
        """从分析文本中提取 weak_counters 数据"""
        results: list[dict] = []

        # 找到 weak_counters 字段，其后跟着 StrongCounter(...) 列表
        idx = text.find("weak_counters")
        if idx < 0:
            return results

        # 从 weak_counters 往后找 StrongCounter(...) 调用
        chunk = text[idx:]
        for m in re.finditer(
            r'StrongCounter\((\d+),"(\w+)",(\d+),(\d+),([\d.]+)\)',
            chunk,
        ):
            name = m.group(2)
            try:
                wr = round(float(m.group(5)) * 100, 1)
            except ValueError:
                wr = None
            results.append({"name": name, "winRateAgainst": wr})

        if not results:
            logger.debug("未能解析 Counter 数据")
        return results[:10]

    # ── 缓存 ──────────────────────────────────────────────

    @staticmethod
    def _load_cache(filepath: Path, ignore_ttl: bool = False) -> Any | None:
        if not filepath.exists():
            return None
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            if ignore_ttl:
                return data
            updated = data.get("last_updated")
            if updated:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(updated)
                if age.total_seconds() < CACHE_TTL_HOURS * 3600:
                    return data
            return None
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _load_raw_cache(filepath: Path) -> dict:
        if not filepath.exists():
            return {}
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _save_cache(filepath: Path, data: Any):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
