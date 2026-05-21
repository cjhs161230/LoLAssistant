# 🎯 LoL 智能选人助手

> 一款在英雄联盟选人阶段推荐最佳英雄的桌面工具。综合**版本强势 + 克制对手 + 个人擅长 + 团队适配**四个维度打分，输出 Top 3 推荐。

![Python](https://img.shields.io/badge/Python-3.11+-blue) [![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

## 功能特性

- **四维推荐算法**：版本强度(40%) + 克制关系(30%) + 个人擅长(20%) + 团队适配(10%)，权重可配置
- **现代化 Web 界面**：Vue3 + Tailwind CSS 暗黑风格，浏览器内运行
- **中文搜索**：支持中文名、英文名、外号模糊匹配（盲僧→李青、奥巴马→卢锡安）
- **完全离线**：`--download-all` 一次性下载全部数据，之后无需联网

## 本地部署

### 环境要求

| 项目 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.10+ | [官网下载](https://www.python.org/downloads/) |
| 操作系统 | Windows 10/11 | 手动模式可跨平台（macOS/Linux 未测试） |
| 网络 | 首次部署需联网 | 下载数据后完全离线可用 |

### 第一步：克隆项目

```bash
git clone https://github.com/你的用户名/LoLAssistant.git
cd LoLAssistant
```

### 第二步：安装依赖

```bash
# 推荐：先创建虚拟环境
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate       # Windows CMD
# 或
.\venv\Scripts\Activate.ps1  # Windows PowerShell

# 安装依赖
pip install -r requirements.txt
```

依赖清单（`requirements.txt`）：

```
requests
urllib3
PySimpleGUI
```

### 第三步：下载离线数据

```bash
# 一次性下载全部 172 个英雄的 Tier + Counter 数据
# 5 线程并发，约 30 秒完成
python main.py --download-all
```

下载内容：

| 数据 | 文件 | 大小 | 说明 |
|------|------|------|------|
| 版本 Tier | `data/meta_cache.json` | ~55KB | 5 个位置 × 各英雄胜率排行，24h 自动刷新 |
| 克制关系 | `data/counter_cache.json` | ~32KB | 全部 172 英雄的 Counter 数据 |
| 英雄属性 | `data/champion_attributes.json` | ~33KB | 伤害类型、角色、位置（随项目分发） |
| 中文映射 | `data/champion_names_cn.json` | ~27KB | 中文名 + 120+ 外号（随项目分发） |

> **注意**：项目已经附带预下载的数据文件，`--download-all` 仅在数据过期或首次克隆时需要执行。

### 第四步：验证安装

```bash
# 运行演示模式，确认一切正常
python main.py --demo
```

正常输出应包含：
```
LoL 智能选人助手 v1.0 [演示模式]
已加载 5 个位置的 Tier 数据
已加载 Yasuo 的 Counter 数据 (6 个克制英雄)
```

同时会弹出推荐结果窗口，显示中单对阵亚索的 Top 3 推荐。

### 第五步：启动 Web 界面

```bash
python main.py
```

浏览器自动打开 `http://127.0.0.1:5732`，进入选人界面：

1. 选择你的位置（上单/打野/中单/ADC/辅助）
2. 搜索英雄（支持中文/外号）→ 点击 → 加入对手/我方/Ban
3. 点「生成推荐」→ 实时展示 Top 3，含分数条和推荐理由

### 其他运行模式

```bash
python main.py --manual        # PySimpleGUI 桌面版（旧版）
python main.py --demo          # 演示模式：模拟场景，无需手动填写
python main.py --download-all  # 重新下载全部数据（更新版本）
python main.py --lcu           # LCU 模式：国际服自动检测（国服不可用）
```

### 常见问题

**Q: 启动报错 `No module named 'PySimpleGUI'`**

```bash
pip install PySimpleGUI
```

**Q: 数据过期了怎么办？**

```bash
# 强制刷新 Tier 数据（删除缓存重新拉取）
del data\meta_cache.json
python main.py --download-all
```

**Q: 能否在 macOS/Linux 上运行？**

手动模式可以，因为只依赖 Python + PySimpleGUI。LCU 连接模块仅适配 Windows。

**Q: 个人数据怎么录入？**

启动后点「管理擅长英雄」→ 搜索你的常用英雄 → 输入场次和胜场 → 保存。数据存储在 `data/personal_champions.json`。

## 使用流程

1. 选择你的位置（上单/打野/中单/ADC/辅助）
2. 在左侧搜索框输入英雄（支持盲僧、奥巴马、压缩等俗称）
3. 点击搜索结果 → 右侧弹出快捷按钮 → 「加到对手/我方/Ban」
4. 选好后点「生成推荐」→ 显示 Top 3 推荐，含分数条和推荐理由
5. 可随时点右上角「擅长英雄」录入个人数据，参与个人擅长分计算

## 推荐算法

```
推荐总分 = 版本强度分×0.40 + 克制分×0.30 + 个人擅长分×0.20 + 团队适配分×0.10
```

| 维度 | 权重 | 数据来源 |
|------|------|----------|
| 版本强度 | 40% | OP.GG 国服 Tier 列表（T0→100分, T5→20分） |
| 克制关系 | 30% | OP.GG 对位胜率数据（胜率55% → 映射100分） |
| 个人擅长 | 20% | 手动录入的英雄场次胜率数据 |
| 团队适配 | 10% | 英雄属性分析（补AP/坦克/控制各+20分） |

## 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 语言 | Python 3.10+ | 后端 API + 推荐引擎 |
| Web 框架 | Flask 3.x | REST API 服务 |
| 前端 | Vue 3 + Tailwind CSS | 暗黑风格 Web 界面 |
| HTTP | requests | OP.GG API 调用 |
| 数据源 | OP.GG MCP API | Tier 数据 + Counter 数据 |
| 英雄数据 | 腾讯 CDN | 中文名 + 外号映射 (172英雄) |
| 存储 | JSON 文件 | 本地缓存 |

## 项目结构

```
LoLAssistant/
├── server.py                # Flask API 服务（Web 模式后端）
├── main.py                  # 程序入口，模式分发
├── recommendation_engine.py # 四维推荐算法核心
├── meta_fetcher.py          # OP.GG 数据采集 + 缓存管理
├── gui.py                   # 桌面 GUI（PySimpleGUI，--manual 模式）
├── lcu_connector.py         # LCU API 连接（国际服）
├── config.py                # 配置常量（权重/路径/缓存策略）
├── requirements.txt         # Python 依赖
│
├── static/                  # Web 前端
│   └── index.html           # Vue3 + Tailwind CSS 界面
│
├── data/                    # 本地数据
│   ├── champion_attributes.json   # 英雄属性（172个）
│   ├── champion_names_cn.json     # 中文名+外号映射
│   ├── meta_cache.json            # 版本 Tier 数据（24h TTL）
│   ├── counter_cache.json         # 全英雄 Counter 关系
│   └── personal_champions.json    # 个人擅长英雄
│
└── docs/
    ├── ARCHITECTURE.md      # 架构设计
    └── DEV_LOG.md           # 开发记录
```

## 已知限制

| 限制 | 说明 |
|------|------|
| 国服 LCU 认证 | WeGame 版不写入 lockfile 密码，无法自动检测选人（需手动填写） |
| 段位过滤 | OP.GG API 不支持按玩家段位过滤，Tier 数据为全段位聚合 |
| 个人数据 | OP.GG 不支持国服召唤师查询，需在界面中手动录入擅长英雄 |
| 仅 Windows | LCU 连接逻辑仅适配 Windows 路径（Web 模式可跨平台运行） |

详见 [docs/DEV_LOG.md](docs/DEV_LOG.md)。

## 许可证

MIT License
