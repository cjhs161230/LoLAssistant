# 架构设计文档

> 原始设计：最初的开发设计想法.txt  
> 最后更新：2026-05-21（Web 模式）

## 设计原则

- **极简**：代码量控制在 1500 行以内
- **单人使用**：不需要多用户/登录系统
- **本地运行**：不需要云服务器
- **国服优先**：数据以国服为主
- **前后端分离**：Flask API + Vue3/Tailwind 前端

## 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    main.py (入口)                     │
│        解析运行模式 → 分发到对应入口                    │
│                                                       │
│  ┌────────────  Web 模式（默认）──────────────────┐   │
│  │                                                 │   │
│  │  [浏览器] ←→ [static/index.html]                │   │
│  │      │          Vue3 + Tailwind CSS             │   │
│  │      │  REST API (JSON)                         │   │
│  │      ▼                                          │   │
│  │  [server.py] ← Flask API 服务                   │   │
│  │      │                                          │   │
│  │      ├── /api/champions    → 英雄列表             │   │
│  │      ├── /api/tier-list    → 版本 Tier 数据       │   │
│  │      ├── /api/recommend    → 推荐结果             │   │
│  │      ├── /api/personal     → 个人英雄数据         │   │
│  │      └── /api/stats        → 缓存统计             │   │
│  │                                                 │   │
│  └───────────────┬─────────────────────────────────┘   │
│                  │                                      │
│  ┌───────────────┼─────────────────────────────────┐   │
│  │               ▼               │                   │   │
│  │  ┌───────────┐  ┌───────────┐  ┌──────────────┐  │   │
│  │  │lcu_connector│ │meta_fetcher│ │recommendation │  │   │
│  │  │   .py      │  │   .py     │  │ _engine.py   │  │   │
│  │  │            │  │           │  │              │  │   │
│  │  │ 连接LCU    │  │ OP.GG API │  │ 四因子排序    │  │   │
│  │  │ (国际服)   │  │ Tier/Cntr │  │ Top3推荐     │  │   │
│  │  └────────────┘  └───────────┘  └──────────────┘  │   │
│  │                                                   │   │
│  │  ┌────────────┐                                   │   │
│  │  │  gui.py    │  ← PySimpleGUI 桌面版（旧）        │   │
│  │  │  --manual  │    保留，通过 --manual 启动        │   │
│  │  └────────────┘                                   │   │
│  └───────────────────────────────────────────────────┘   │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │                data/ (JSON 文件)                  │    │
│  │  meta_cache.json          — 版本英雄胜率缓存      │    │
│  │  counter_cache.json       — Counter 关系缓存     │    │
│  │  champion_names_cn.json   — 中文名+外号映射      │    │
│  │  champion_attributes.json — 英雄属性表           │    │
│  │  personal_champions.json  — 个人擅长数据         │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## 数据流

```
[OP.GG MCP API] ←→ [meta_fetcher.py] ──→ [recommendation_engine.py]
                                               │
[腾讯 CDN] ←→ [champion_names_cn.json] ←───────┤
                                               │
[用户] ←→ [Vue3 前端] ←→ [server.py API] ←────┤
                                               │
                                               ▼
                                     [推荐结果 JSON] ──→ 浏览器渲染
```

## 模块说明

### main.py — 模式分发入口

解析命令行参数，分发到不同入口：

| 模式 | 命令 | 入口函数 | 说明 |
|------|------|----------|------|
| Web | `python main.py`（默认） | `server.start_server()` | Flask + Vue3 前端 |
| 手动 | `python main.py --manual` | `manual_main()` | PySimpleGUI 桌面版 |
| 演示 | `python main.py --demo` | `demo_main()` | 模拟场景测试 |
| 下载 | `python main.py --download-all` | `download_all()` | 全量离线数据 |

### server.py — Flask API 服务

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/champions` | GET | 172 个英雄中英文名 + 外号 |
| `/api/tier-list` | GET | 版本各位置 Tier 数据 |
| `/api/recommend` | POST | 生成推荐（position + enemy/team/ban） |
| `/api/personal` | GET/POST | 个人擅长英雄 CRUD |
| `/api/stats` | GET | 缓存统计信息 |

启动时自动打开浏览器访问 `http://127.0.0.1:5732`。

### static/index.html — Vue3 前端

- **技术栈**：Vue 3 CDN + Tailwind CSS CDN，零构建依赖
- **暗黑主题**：GitHub Dark 风格 + LoL 金色强调
- **玻璃拟态**：毛玻璃卡片 + 模糊背景
- **功能**：位置选择 / 英雄搜索 / 对手我方Ban管理 / 推荐展示 / 个人数据管理

### recommendation_engine.py — 推荐引擎

四维度加权打分：
```
推荐总分 = 版本强度×0.40 + 克制×0.30 + 个人×0.20 + 团队×0.10
```

- **版本强度**：Tier 1→100分, Tier 5→20分
- **克制关系**：(对位胜率-45)×2 映射到 0-100，多对手取均值
- **个人擅长**：≥20场直接用胜率，5-19场降权，<5场默认50分
- **团队适配**：缺AP+20，缺坦克+20，缺控制+20，上限100

### meta_fetcher.py — 数据采集

- OP.GG MCP API 拉取国服 Tier + Counter 数据
- 24h TTL 缓存，过期自动刷新
- 线程池并发预加载（5线程）
- `--download-all` 全量下载 172 英雄

### lcu_connector.py — LCU 连接（国际服）

- 标准版：lockfile → riot:password Basic 认证
- WeGame 版：通过 Riot Client API 间接连接（认证受限）
- 轮询检测选人阶段

### config.py — 配置

- 推荐权重、Tier 分数映射
- 缓存策略、请求延迟
- 团队适配加分规则

## 数据源

| 数据 | 来源 | 用途 |
|------|------|------|
| Tier 列表 | OP.GG MCP API (region=cn) | 各位置英雄胜率排行 |
| Counter 数据 | OP.GG MCP API | 对位克制关系 + 胜率 |
| 英雄中文名+外号 | 腾讯 CDN (game.gtimg.cn) | 172 英雄中英文搜索映射 |
| 英雄属性 | 本地 JSON | 伤害类型、角色、位置、控制 |
| 个人数据 | 本地 JSON | 用户手动录入的擅长英雄 |
