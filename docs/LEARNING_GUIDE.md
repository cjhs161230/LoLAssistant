# 项目学习指南 — LoL 智能选人助手

> 这份文档帮助你深入理解项目，在面试或简历中自信地介绍它。

---

## 一、项目一句话介绍

> 一个 Python 全栈项目：通过 OP.GG 数据 + 自研推荐算法，在英雄联盟选人阶段智能推荐最佳英雄。后端 Flask + 前端 Vue3，支持中文模糊搜索，完全离线运行。

## 二、技术栈全貌

| 层级 | 技术 | 掌握程度 |
|------|------|----------|
| 语言 | Python 3.10+ | 类、装饰器、类型注解、模块化 |
| Web 后端 | Flask | RESTful API、路由、CORS、静态文件服务 |
| Web 前端 | Vue 3 + Tailwind CSS | 响应式数据、组件化思维、CDN 引入 |
| HTTP 客户端 | requests | Session、超时、异常处理、SSL |
| 数据处理 | JSON | 读写、缓存策略、TTL 过期 |
| 并发 | threading / ThreadPoolExecutor | 线程池、后台任务、线程安全 |
| 桌面 GUI | PySimpleGUI | 事件循环、系统托盘、弹窗 |
| 外部 API | OP.GG MCP | JSON-RPC 协议、API 调用封装 |
| 打包 | pip + requirements.txt | 依赖管理 |

## 三、你为什么做这个项目

**痛点**：打英雄联盟排位时，选人阶段只有 30 秒，来不及查 Counter 关系、版本胜率、个人数据。

**解决方案**：做一个本地工具，提前把所有数据下载好，选人时手动勾选对手英雄，一键出 Top 3 推荐。

**技术动机**：想用 Python 做一个完整的全栈项目，从前端到后端到数据层全自己写。

## 四、核心算法 — 你可能被问到的

### 四维加权推荐算法

```
推荐总分 = 版本强度 × 0.40 + 克制关系 × 0.30 + 个人擅长 × 0.20 + 团队适配 × 0.10
```

**1. 版本强度分（40%权重）**
- 来源：OP.GG 国服 Tier 列表
- Tier 1 → 100分，Tier 5 → 20分
- 代码位置：`recommendation_engine.py` → `_calc_meta()`

**2. 克制分（30%权重）**
- 来源：OP.GG Counter 数据（对位胜率）
- 公式：`(对位胜率 - 45) × 2`，映射到 0-100
- 多个对手取平均值
- 代码位置：`recommendation_engine.py` → `_calc_counter()`

**3. 个人擅长分（20%权重）**
- ≥20场：直接用胜率（如 62% → 62分）
- 5-19场：胜率 × (场次/20)，降低权重
- <5场：默认 50 分
- 代码位置：`recommendation_engine.py` → `_calc_personal()`

**4. 团队适配分（10%权重）**
- 缺 AP 伤害 → AP 英雄 +20分
- 缺前排坦克 → 坦克英雄 +20分
- 缺控制技能 → 控制英雄 +20分
- 总分上限 100
- 代码位置：`recommendation_engine.py` → `_calc_team()`

### 面试可能问：权重为什么这样设？

版本强度是最重要的参考（40%），因为版本强势英雄天然胜率高。克制关系次之（30%），对线 Counter 直接影响对局。个人擅长再次之（20%），因为熟练度影响发挥但不如版本和 Counter 关键。团队适配最低（10%），因为路人局阵容完整性不如前三个因素重要。

## 五、架构设计 — 你可能被问到的

### 为什么选 Flask + Vue3 而不是纯桌面 GUI？

一开始用的 PySimpleGUI，但界面太丑、交互不流畅、无法做复杂布局。换成 Flask + Vue3：
- 前端可以做到现代化 UI（暗黑玻璃拟态），而 PySimpleGUI 控件极其有限
- 前后端分离，后端只负责数据和算法，前端只管展示
- 浏览器打开即用，不需要安装桌面框架

### 前后端怎么通信？

全部走 RESTful JSON API，共 6 个端点：

| 端点 | 方法 | 作用 |
|------|------|------|
| `/api/champions` | GET | 172英雄列表（中英文+外号） |
| `/api/tier-list` | GET | 版本Tier数据 |
| `/api/recommend` | POST | 核心：根据选人信息返回推荐 |
| `/api/personal` | GET/POST | 个人英雄数据CRUD |
| `/api/stats` | GET | 缓存状态 |
| `/api/preload` | POST | 批量预加载Counter数据 |

### 数据怎么存储？

全部用本地 JSON 文件，不用数据库：
- `meta_cache.json` — 版本 Tier 数据，24小时过期
- `counter_cache.json` — 173英雄克制关系，永久缓存
- `champion_names_cn.json` — 中文名+外号映射
- `champion_attributes.json` — 英雄属性（伤害类型/角色/位置）
- `personal_champions.json` — 用户录入的擅长英雄

**为什么不用数据库？** 数据量太小（总共不到 200KB），JSON 文件零配置、零依赖，读写只需要 `json.load/dump`。

### 并发预加载怎么做的？

启动时用 `ThreadPoolExecutor`（5线程）并发拉取 34 个热门英雄的 Counter 数据。8 秒内完成，GUI 可立即使用。

代码位置：`meta_fetcher.py` → `preload_counters_batch()`

### 中文搜索怎么实现？

从腾讯 CDN 拉取官方中文英雄名 + keywords 字段（含外号），建立英文名到中文名+搜索词的映射。用户在输入框输入"盲僧"时，匹配到 `LeeSin` 的搜索词列表中的"盲僧"。

代码位置：`gui.py` → `_match_hero()` / `static/index.html` → `searchChampions()`

## 六、踩过的坑 — 面试加分项

### 坑1：WeGame 国服 LCU 认证

想实现"检测到用户进入选人阶段自动弹窗"，需要连接游戏客户端 LCU API。但国服用 WeGame 启动，LCU 认证密码不写入 lockfile。尝试了 WMI 读进程、Riot Client Token 代理、空密码认证等7种方案全部失败。**最终决策：改为手动模式。**

经验：遇到不可逾越的第三方限制时，改变交互方式比死磕技术壁垒更务实。

### 坑2：OP.GG MCP API 不支持段位过滤

想实现"根据玩家段位显示不同 Tier 数据"，但 API 返回全段位聚合数据，拒绝了所有 tier/rank/league 参数。尝试了直接抓取 OP.GG 网页（被反爬 202 拦截）和 U.GG（403 拦截）。

经验：第三方 API 的能力边界需要尽早验证，避免投入过多时间。

### 坑3：大小写匹配 Bug

推荐结果是英文名（Yasuo）而不是中文名（亚索），查了好久发现是 `cn_data.get(en_name.lower())` 但 JSON 键是 PascalCase（`Yasuo` 不是 `yasuo`）。改成大小写不敏感遍历才修复。

经验：JSON 键的大小写问题非常隐蔽，调试时先打印实际键名。

## 七、代码走读 — 面试时可能让你现场讲

### 如果面试官问："讲讲 `recommendation_engine.py`"

```
入口是 recommend() 方法，接收参数后：
1. _filter_pool() — 从全部英雄中排除被 Ban 的、已被选的、你不拥有的
2. 对候选池中每个英雄：
   - _calc_meta() — 查 Tier 列表打分
   - _calc_counter() — 查 Counter 数据打分
   - _calc_personal() — 查个人战绩打分
   - _calc_team() — 分析我方阵容打分
   - 加权求和
3. _gen_reasons() — 为每个推荐生成可读理由
4. 按总分降序，返回 Top 3
```

### 如果面试官问："讲讲 `server.py` 的 `/api/recommend`"

```
1. 接收 JSON：position + enemy_names + team_names + ban_names
2. 用 en_to_id 映射把英文名转成 champion ID
3. 遍历 enemy_ids，检查 counter_cache 是否已有数据
   - 没有的调用 fetcher.get_counter_data() 拉取
   - 结果写入 counter_cache 并持久化到 JSON 文件
4. 加载 personal_champions.json（如果有的话）
5. 调用 engine.recommend() 执行推荐
6. 返回 JSON 给前端
```

### 如果面试官问："这个项目有哪些可以改进的地方？"

1. 个人数据录入目前手动，可以接入 LCU API（国际服）自动同步
2. Counter 预加载目前是启动时全跑一遍，可以用增量+定时刷新
3. 前端目前是单文件，可以拆分成 Vue 组件
4. 没有单元测试，可以加 pytest
5. 可以打包成 Docker 一键部署

## 八、面试常见问答

**Q: 为什么做这个项目？**
A: 我自己打 LOL 排位，选人时间很短来不及查数据，就想到用 Python 做个工具。顺便练一下全栈开发。

**Q: 遇到的最大挑战？**
A: 两个。一是 WeGame 国服 LCU 认证走不通，试了 7 种方案后决定改为手动模式。二是 OP.GG API 不支持段位过滤，花了很多时间验证 API 边界。

**Q: 前后端怎么通信？**
A: RESTful API。Flask 起 6 个 JSON 端点，Vue3 前端用 fetch 调用。没有用 WebSocket，因为这个场景不需要实时推送。

**Q: 数据从哪来？**
A: OP.GG MCP API 拉取 Tier + Counter 数据，腾讯 CDN 拉取中文英雄名。全部缓存到本地 JSON，24h 过期自动刷新。

**Q: 推荐算法的权重为什么这样设计？**
A: 版本强度 40% 最重要（版本决定英雄强度），Counter 30% 次之（对线克制直接影响胜负），个人擅长 20%（熟练度重要但非决定因素），团队适配 10%（路人局阵容完整性影响较小）。

**Q: 这个项目能上线吗？**
A: 目前是本地工具。要上线需要加账号系统、数据库、服务器部署。但作为个人学习项目没必要。

## 九、简历怎么写

### 项目经历 — LoL 智能选人助手

**技术栈**：Python / Flask / Vue3 / Tailwind CSS / ThreadPoolExecutor / JSON

**项目描述**：独立开发的全栈桌面工具，通过 OP.GG 数据源 + 自研四维加权推荐算法，在英雄联盟选人阶段推荐最优英雄选择。

**核心工作**：
- 设计并实现了四维加权推荐算法（版本强度/克制关系/个人擅长/团队适配），综合打分排序
- 搭建 Flask REST API 后端（6 个端点），Vue3 + Tailwind CSS 构建现代化暗黑前端
- 实现英雄中文模糊搜索（172 英雄 + 120+ 民间外号），从腾讯 CDN 拉取官方数据映射
- 使用 ThreadPoolExecutor 实现 5 线程并发数据预加载，启动速度从 30 秒优化到 8 秒
- 设计本地 JSON 缓存策略（24h TTL），支持完全离线运行

**技术亮点**：
- 前后端分离架构，RESTful API 设计
- 并发数据采集与缓存管理
- 自定义评分算法与候选池筛选逻辑
- 暗黑玻璃拟态 UI 设计

---

> 最后提醒：面试时真诚最重要，能讲清楚你做的每一个决定（为什么这样设计、为什么不那样设计）比背术语管用得多。
