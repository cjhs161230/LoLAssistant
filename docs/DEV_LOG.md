# 开发记录

> 最后更新：2026-05-21

## 版本历史

### v1.1 (2026-05-21) — Web 模式

**新增：**
- ✅ Flask REST API（`server.py`）：6 个端点
- ✅ Vue3 + Tailwind CSS 暗黑前端（`static/index.html`）
- ✅ 默认 Web 模式：`python main.py` 启动后自动打开浏览器
- ✅ 版本 Tier 排行榜（左栏，切换位置自动更新）
- ✅ 个人英雄管理弹窗（添加/编辑/删除擅长英雄）

**已知限制：**
- ⚠️ OP.GG MCP API 不支持按玩家段位过滤数据，Tier 排行显示全段位聚合
- ⚠️ 不支持国服召唤师战绩自动查询（需手动录入擅长英雄）

**保留：**
- ✅ PySimpleGUI 桌面版（`--manual`）
- ✅ 演示模式（`--demo`）
- ✅ 全量下载（`--download-all`）

### v1.0 (2026-05-21) — 手动模式发布

**已完成：**
- ✅ 推荐引擎：四维打分（版本40% + 克制30% + 个人20% + 团队10%）
- ✅ 数据采集：OP.GG MCP API 拉取国服 Tier + Counter 数据
- ✅ 中文搜索：172 英雄中文名 + 120+ 外号映射（腾讯 CDN）
- ✅ 完全离线：`--download-all` 一次性全量下载
- ✅ 个人管理：手动录入擅长英雄的场次胜率
- ✅ 系统托盘 + 推荐弹窗 + 仪表盘（PySimpleGUI）
- ✅ 并发预加载：5 线程后台拉取热门英雄 Counter 数据

## 运行模式

```bash
python main.py                 # Web 模式（默认）
python main.py --manual        # PySimpleGUI 桌面版
python main.py --demo          # 演示模式
python main.py --download-all  # 全量下载离线数据
python main.py --lcu           # LCU 模式（国际服）
```

## 核心问题：WeGame 国服 LCU API 无法认证

这是项目无法实现全自动选人检测的根本原因。

### 背景

中国国服英雄联盟通过 WeGame 启动，使用腾讯定制版客户端（`patchline: Tencent`）。认证机制由 `wegame_auth.dll` 和 `wxlogin.dll` 接管。

### 已确认的事实

- LCU API 端口可发现（57851），但 lockfile 为 0 字节（未写入密码）
- Tencent 定制版使用 `rso_platform_id: TENCENT`，认证机制与标准版完全不同
- Riot Client API 部分可用（可获取召唤师名和 PUUID），但无权访问 LCU 核心端点
- TenProtect/AntiCheatExpert 拦截跨进程内存访问

### 已尝试但失败的方案

| 方案 | 结果 | 原因 |
|------|------|------|
| 读取标准 lockfile | 文件 0 字节 | WeGame 未写入密码 |
| WMI 读进程命令行 | 无实例 | 非运行时可读，且参数不含密码 |
| ReadProcessMemory | 错误码 5 | 反作弊拦截 |
| `riot:""` 空密码认证 | 401 | 密码错误 |
| Riot Client Bearer token | 403 | 无 LCU 数据访问权限 |

### 替代方案

采用**手动填写模式**——用户在 GUI 或 Web 界面中自行输入选人信息，程序基于预加载的离线数据生成推荐。推荐引擎的核心功能完全不受影响。

## 数据时效性

- **Tier 数据**：24 小时 TTL，过期自动刷新；断网降级使用旧缓存
- **Counter 数据**：全量下载后永久缓存；`--download-all` 用于更新
- **OP.GG 不支持国服召唤师查询**，个人数据需手动录入
