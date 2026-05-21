"""LCU 连接模块 - 支持标准版和国服 WeGame 版"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

import requests
import urllib3

from config import LCU_LOCKFILE_CANDIDATES

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class LCUConnector:
    """连接 League Client，自动适配标准版和 WeGame 国服版"""

    def __init__(self):
        self._base_url: str | None = None
        self._auth: tuple[str, str] | None = None
        self._connected = False
        self._is_wegame = False
        # WeGame 版备用连接（通过 Riot Client API）
        self._rc_base_url: str | None = None
        self._rc_auth: tuple[str, str] | None = None

    # ── 连接管理 ──────────────────────────────────────────

    def connect(self) -> bool:
        """尝试连接 LCU，先试标准 lockfile，再试 WeGame"""
        # 1. 标准方式：读取 lockfile
        if self._connect_lockfile():
            return True

        # 2. WeGame 方式：通过 Riot Client 间接获取
        if self._connect_wegame():
            return True

        return False

    def _connect_lockfile(self) -> bool:
        """标准方式：读取 lockfile 连接"""
        lockfile_path = self._find_lockfile()
        if not lockfile_path:
            return False
        try:
            raw = lockfile_path.read_text().strip()
            if not raw or ":" not in raw:
                return False
            data = raw.split(":")
            if len(data) < 5:
                return False
            _, pid, port, password, protocol = data[:5]
            self._base_url = f"{protocol}://127.0.0.1:{port}"
            self._auth = ("riot", password)
            self._connected = True
            self._is_wegame = False
            logger.info("已连接 LCU (PID=%s, Port=%s)", pid, port)
            return True
        except Exception:
            return False

    def _connect_wegame(self) -> bool:
        """WeGame 方式：通过 Riot Client API 发现 LCU 端口"""
        # 先读 Riot Client lockfile
        rc_lockfiles = [
            r"E:\WeGameApps\英雄联盟\Riot Client Data\User Data\Config\lockfile",
        ]
        rc_info = None
        for p in rc_lockfiles:
            path = Path(p)
            if path.exists():
                try:
                    raw = path.read_text().strip()
                    if raw and ":" in raw:
                        parts = raw.split(":")
                        if len(parts) >= 4:
                            _, rc_pid, rc_port, rc_pwd, rc_proto = parts[:5]
                            rc_info = (rc_pid, rc_port, rc_pwd, rc_proto)
                            break
                except Exception:
                    continue

        if not rc_info:
            return False

        _, rc_port, rc_pwd, rc_proto = rc_info
        self._rc_base_url = f"{rc_proto}://127.0.0.1:{rc_port}"
        self._rc_auth = ("riot", rc_pwd)

        # 使用 Riot Client API 查找 League Client LCU 端口
        league_port = self._discover_lcu_port()
        if not league_port:
            logger.warning("无法发现 LCU 端口")
            return False

        # 对于 WeGame 版，我们连接到 LCU 但后续请求可能返回 401/403
        # 这里标记为已连接，请求会尝试发送，失败时返回 None
        self._base_url = f"https://127.0.0.1:{league_port}"
        self._auth = ("riot", "")  # 密码未知，后续请求会处理 401
        self._connected = True
        self._is_wegame = True
        logger.info("已连接 WeGame 版 LCU (Port=%s)，功能可能受限", league_port)
        return True

    def _discover_lcu_port(self) -> int | None:
        """通过 netstat 查找 LeagueClient.exe 的 LCU 端口"""
        try:
            r = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            # 找 LeagueClient.exe 的 PID
            pid_task = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq LeagueClient.exe",
                 "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            pid = None
            for line in pid_task.stdout.strip().split("\n"):
                if "LeagueClient.exe" in line:
                    parts = line.split(",")
                    if len(parts) >= 2:
                        pid = parts[1].strip('"')
                        break
            if not pid:
                return None

            # 在 netstat 输出中找该 PID 的 LISTENING 端口
            for line in r.stdout.splitlines():
                if "LISTENING" in line and pid in line:
                    # 解析地址:端口
                    parts = line.split()
                    if len(parts) >= 2:
                        addr = parts[1]
                        if ":" in addr:
                            port_str = addr.rsplit(":", 1)[-1]
                            try:
                                return int(port_str)
                            except ValueError:
                                continue
        except Exception as e:
            logger.debug("发现 LCU 端口失败: %s", e)
        return None

    def disconnect(self):
        self._connected = False
        self._base_url = None
        self._auth = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def is_wegame(self) -> bool:
        return self._is_wegame

    # ── 请求封装 ──────────────────────────────────────────

    def _request(self, method: str, endpoint: str) -> Any:
        if not self._connected or not self._base_url:
            return None
        url = f"{self._base_url}{endpoint}"
        try:
            resp = requests.request(
                method, url, auth=self._auth, verify=False, timeout=5
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            if resp.status_code in (401, 403) and self._is_wegame:
                # WeGame 版需要尝试用 Riot Client token 做 Bearer 认证
                return self._request_with_bearer(method, endpoint)
            logger.debug("LCU %s %s → %s", method, endpoint, resp.status_code)
            return None
        except requests.ConnectionError:
            logger.warning("LCU 连接断开")
            self._connected = False
            return None
        except Exception as e:
            logger.debug("LCU 请求异常: %s", e)
            return None

    def _request_with_bearer(self, method: str, endpoint: str) -> Any:
        """WeGame 版：从 Riot Client 获取 token 后用 Bearer 认证访问 LCU"""
        if not self._rc_base_url or not self._rc_auth:
            return None
        try:
            # 从 Riot Client 获取 RSO token
            url = f"{self._rc_base_url}/rso-auth/v1/authorization/access-token"
            resp = requests.get(url, auth=self._rc_auth, verify=False, timeout=3)
            if resp.status_code == 200:
                token = resp.json().get("token", "")
                if token:
                    headers = {"Authorization": f"Bearer {token}"}
                    url2 = f"{self._base_url}{endpoint}"
                    resp2 = requests.request(
                        method, url2, headers=headers, verify=False, timeout=5
                    )
                    if resp2.status_code == 200:
                        return resp2.json()
        except Exception:
            pass
        return None

    def _rc_request(self, endpoint: str) -> Any:
        """直接请求 Riot Client API"""
        if not self._rc_base_url or not self._rc_auth:
            return None
        url = f"{self._rc_base_url}{endpoint}"
        try:
            resp = requests.get(url, auth=self._rc_auth, verify=False, timeout=5)
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None

    def _get(self, endpoint: str) -> Any:
        return self._request("GET", endpoint)

    # ── 核心 API ──────────────────────────────────────────

    def get_current_summoner(self) -> dict | None:
        """获取当前登录召唤师信息"""
        result = self._get("/lol-summoner/v1/current-summoner")
        if result:
            return result
        # WeGame 版从 Riot Client Chat API 获取
        chat = self._rc_request("/chat/v1/session")
        if chat:
            return {
                "displayName": chat.get("game_name", ""),
                "puuid": chat.get("puuid", ""),
                "summonerLevel": 0,
                "gameName": chat.get("game_name", ""),
                "gameTag": chat.get("game_tag", ""),
            }
        return None

    def get_champ_select_session(self) -> dict | None:
        """获取选人阶段 session"""
        return self._get("/lol-champ-select/v1/session")

    def get_owned_champions(self) -> list[dict] | None:
        """获取拥有的英雄列表"""
        return self._get("/lol-champions/v1/owned-champions-minimal")

    def get_personal_stats(self, puuid: str) -> dict | None:
        """获取个人英雄统计数据"""
        result = self._get(f"/lol-career-stats/v1/summoner-stats/{puuid}")
        if result:
            return result
        # WeGame 版通过 Riot Client 尝试
        return None

    # ── 辅助 ──────────────────────────────────────────────

    @staticmethod
    def _find_lockfile() -> Path | None:
        for path_str in LCU_LOCKFILE_CANDIDATES:
            p = Path(path_str)
            if p.exists():
                return p
        return None

    def wait_for_client(self, timeout: float = 300, interval: float = 2) -> bool:
        """等待客户端启动并连接"""
        start = time.time()
        while time.time() - start < timeout:
            if self.connect():
                return True
            time.sleep(interval)
        return False

    def wait_for_champ_select(self, timeout: float = 600,
                              interval: float = 3) -> dict | None:
        """轮询等待进入选人阶段"""
        start = time.time()
        while time.time() - start < timeout:
            if not self.connected:
                if not self.connect():
                    time.sleep(interval)
                    continue
            session = self.get_champ_select_session()
            if session and self._is_in_champ_select(session):
                return session
            time.sleep(interval)
        return None

    @staticmethod
    def _is_in_champ_select(session: dict) -> bool:
        timer = session.get("timer", {})
        phase = timer.get("phase", "")
        return phase in ("BAN_PICK", "FINDING_MATCH", "MATCH_READY", "PLANNING")
