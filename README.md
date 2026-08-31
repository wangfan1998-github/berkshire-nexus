# BerkshireNexus 🎯

> **拒绝废话与两头讨好**：融合 **Serenity 产业链物理瓶颈** + **Berkshire 价值四大师** + **Qlib 微软多因子量化** 的硬核 AI 投研决策框架。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://python.org)
[![Python Core](https://img.shields.io/badge/Python%20Core-Zero%20Dependencies-orange.svg)](pyproject.toml)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-SKILL.md-black)](SKILL.md)
[![中文优先](https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E4%BC%98%E5%85%88-red)](README.md)
[![English](https://img.shields.io/badge/English-README__EN.md-lightgrey)](README_EN.md)

---

## 💡 为什么写这个项目？

如果你直接问 ChatGPT 或 Claude：“某某股票值不值得买？”，99% 的情况下你会得到这样一段“合格但毫无用处”的废话：

> *“一方面，该公司在 AI 领域有增长潜力，市场空间广阔；但另一方面，宏观环境存在不确定性，且竞争激烈……投资者需结合自身风险承受能力自行决定。”*

**这种分析看似全面客观，但在真金白银的交易决策中价值为零。**

在真实世界里，投资是一门**关于取舍、反偏见、概率与赔率**的残酷博弈。你需要的不是两头下注的套话，而是：
1. **有没有物理级不可替代的供应链瓶颈（Chokepoint）？** （不要听管理层讲故事，看谁卡死了产能）
2. **商业模式能否通过段永平的 5 句话镜子测试？** （5句话说不清楚商业模式赚什么钱，直接不买）
3. **查理·芒格的逆向致死检验（Inversion）**：在什么极端情况下这家公司会死？
4. **格雷厄姆与巴菲特所有者收益（Owner Earnings DCF）**：扣掉虚高的估值泡沫，真实的自由现金流安全边际有多少？
5. **对冲基金风控纪律**：如果买，单一个股仓位上限是多少？什么时候必须止损一票否决？

`BerkshireNexus` 就是为了解决这个问题而诞生的。它吸收并提炼了 GitHub 上顶尖投研项目的思想，构建出一套**强制输出明确结论、多视角对抗、量化数据交叉印证**的现代化投研决策体系。v1.3 又参考了 [`daily_stock_analysis`](https://github.com/ZhuLinsen/daily_stock_analysis) 的数据/新闻证据链和 [`ValueCell`](https://github.com/ValueCell-ai/valuecell) 的 Provider 配置分层，加入当前行情、基本面、新闻引用和可配置 AI 综合；实现为本项目自己的小型、可审计模块，没有整体搬入这些大型项目。

---

## 🏛️ 决策漏斗与工作机制

```
                                【候选股票池 / Tickers】
                                           │
    ┌──────────────────────────────────────┼──────────────────────────────────────┐
    ▼                                      ▼                                      ▼
【1. Serenity 物理瓶颈检验】          【2. Berkshire 大师对抗辩论】          【3. Qlib 多因子量化评分】
• 物理不可替代度 (0-10)               • 巴菲特 (所有者收益/高ROE)            • Quality 质量 (ROE/利润率/负债)
• 扩产周期与 CapEx 壁垒 (0-10)        • 芒格 (逆向思维: 什么会让它死?)       • Value 价值 (前瞻收益率/FCF Yield)
• 5 级瓶颈定级 (Level 1~5)           • 段永平 (商业模式/5句话镜子测试)      • Growth 成长 (营收/EPS 加速度)
• 定价权与供应链利润截留比例         • 李录 / 阿克曼 / 木头姐 对抗裁决     • Momentum 动量 & Low-Beta 风险
    │                                      │                                      │
    └──────────────────────────────────────┼──────────────────────────────────────┘
                                           │
                                           ▼
                      【4. Value-Investing 深度内在价值测算】
                      • 两阶段自由现金流折现模型 (Two-Stage Owner Earnings DCF)
                      • 格雷厄姆防御与成长公式
                      • 真实安全边际 (Margin of Safety %) 测算
                                           │
                                           ▼
                      【5. 对冲基金风控与仓位裁决 (Risk Manager)】
                      • 组合角色定性 (核心基石 / 物理收费站 / 进攻奇兵 / 一票否决)
                      • 动态持仓上限建议 (Max Allocation Cap %)
                      • 离场触发红线 (Redline Inversion Triggers)
                                           │
                                           ▼
                    【📊 最终决策备忘录 (Executive Investment Memo)】
```

---

## 🚀 极速上手 (Quick Start)

Python 核心采用 **零外部依赖（Zero Dependency）** 设计，无需繁琐的 `pip install`；桌面壳层使用 npm 与 Cargo 管理构建依赖。

### 0. macOS 桌面 App（推荐）

桌面端使用 **Tauri 2 + React + TypeScript**，保留现有 Python 研究/学习/风控引擎。它不是网页套壳式行情看板，而是一个本地优先的交易研究操作台：

- Yahoo Finance 最新可用行情/一年日线 + Nasdaq 基本面与公司资料；
- Yahoo Finance 新闻 + SEC EDGAR 官方申报，缺少媒体结果时可回退 Google News RSS；
- 每条新闻都有证据 ID、标题、发布方、发布时间和原文 URL；
- OpenAI-compatible、Ollama、本地 Codex CLI 三种 AI Provider；
- macOS Keychain 独立保存 Binance Key 与 AI Provider Key；
- 总览研究 → 风控 → 模拟成交 → 学习反馈的完整证据链；
- 多股票研究备忘录、Paper 组合与模拟成交账本；
- 可启停的后台 Paper Agent，关闭主窗口后驻留系统托盘；
- Champion / Challenger 学习状态与人工晋升；
- 只能收紧、不能放宽默认值的确定性风控设置；
- macOS Keychain 保存 Binance API Key，并在 App 内做只读预检；
- 每轮周期的本地审计记录；
- Live 模式明确锁定，当前版本不会提交真实订单。

开发运行需要 Node.js 20+、Rust（Cargo）和 Python 3.9+：

```bash
git clone git@github.com:wangfan1998-github/berkshire-nexus.git
cd berkshire-nexus/desktop
npm install
npm run desktop:dev
```

只预览界面（浏览器中会明确显示“演示数据”，不能访问 Keychain 或后台进程）：

```bash
cd desktop
npm run dev
```

构建可安装的桌面应用：

```bash
cd desktop
npm run desktop:build
```

macOS 构建产物位于 `desktop/src-tauri/target/release/bundle/macos/BerkshireNexus.app`，磁盘镜像位于相邻的 `dmg/` 目录。首次从源码运行时，桌面端会自动定位仓库中的 Python 引擎；正式 `.app` 会把 `src/` 作为只读资源打包进去。产品与视觉约束见 [`PRODUCT.md`](PRODUCT.md) 和 [`DESIGN.md`](DESIGN.md)。

#### 在 App 内配置 Binance API Key

1. 在 Binance 网页或官方 App 登录，进入个人资料 → **API 管理**，创建新 API Key 并完成身份验证；
2. 只启用读取权限，不要启用交易、合约或提现；有条件时配置 IP 白名单；
3. 复制 **API Key**，打开 BerkshireNexus → **设置**，粘贴后选择“存入钥匙串”；
4. 运行“只读连通性检查”。本版本不需要 API Secret，也不会开放真实下单。

不要把 API Key 发到聊天、GitHub Issue、截图或提交到 `.env`。Key 保存到 macOS Keychain；前端只读取“是否已配置”，无法回显原文。开户、身份验证、Stocks 资格、API Key 创建与权限设置仍需在 Binance 官方网页或 App 完成。

#### 查看最新价格、新闻并配置 AI 模型

启动桌面 App 后：

1. 打开 **研究**，输入 `AAPL MSFT NVDA`，点击“开始研究”；
2. 结果会分开显示“最新可用价”“行情时间”“基本面期末”“来源追踪”“最新新闻与事件证据”；
3. 打开 **AI 投研**，启用 AI 综合并选择 Provider：
   - **OpenAI-compatible**：填写 Model ID 与 Base URL，把 API Key 存入独立的 macOS Keychain 槽位；兼容 OpenAI、OpenRouter、DeepSeek 等 Chat Completions 服务；
   - **Ollama**：使用本机 `http://127.0.0.1:11434`，无需向本项目提供 Key；
   - **Codex CLI**：使用本机已有的 Codex 登录，每个标的启动一次独立、临时、只读的 `codex exec` 请求，会消耗你的 Codex 用量；它不会偷偷复用当前聊天；
4. 先点击“测试真实连接”，成功后保存配置，再回到研究页运行。

AI 关闭时，行情与新闻仍能独立工作。AI 只接收系统已经抓到的结构化数据和新闻证据，当前新闻陈述必须引用 `N1`、`N2` 等证据 ID；Provider、模型、Prompt 版本、耗时、Token 用量（如果 Provider 返回）与错误都会写进周期审计。AI 输出不会修改确定性综合分或拥有下单权限。

#### 数据可信度不是一句“实时”

| 数据 | 默认来源 | UI 中显示 | 实盘资格 |
|---|---|---|---|
| 最新可用价 / 日线 | Yahoo Finance Chart | 行情时间、市场状态、延迟年龄、Provider | 研究级，非券商权威 |
| 年报 / EPS / 公司资料 | Nasdaq Public API | 财务期末、字段来源、回退字段 | 研究级，非券商权威 |
| 新闻 / 官方事件 | Yahoo Finance Search + SEC EDGAR → Google News RSS | 标题/申报表单、发布方、发布时间、原文、证据 ID | 仅作为研究证据 |
| AI 综合 | 用户选择的 Provider | Provider、模型、引用、耗时、用量、错误 | 无执行权限 |

网络失败时系统会明确显示 `third-party-degraded` 或 `offline-fallback` 以及具体回退字段，不会把预置数据伪装成最新数据。即便所有 Yahoo/Nasdaq 字段齐全，记录仍是 `is_authoritative=false`；Live 风控拒绝用第三方研究数据触发真实买单。

### 1. 命令行自动学习模拟交易 Agent

新版在原有 BerkshireNexus 投研框架之上增加了一个可审计闭环：

```text
BerkshireNexus 分析 → 有界特征 → 自适应收益模型 → Champion/Challenger
       → 目标仓位规划 → 确定性风控 → 持久化模拟成交 → 延迟收益标签
```

运行一次模拟盘周期：

```bash
python3 -m src.cli paper AAPL MSFT NVDA --cash 100000
```

默认状态写入 `.berkshire-nexus/`：

- `paper_portfolio.json`：现金、持仓、当日权益与换手；
- `paper_executions.jsonl`：仅追加的模拟成交日志；
- `learning.json`：分析快照和到期后的前瞻收益标签；
- `model_registry.json`：Champion / Challenger 模型；
- `audits/cycle-*.json`：每轮分析、意图、风控和成交的完整审计记录。

每个分析快照默认等待 20 个日历日再用新价格结算标签，达到 30 个样本后才训练 Challenger。训练集与验证集按时间顺序切分，不随机打乱。模型是透明、带 L2 约束的线性收益模型，只学习各投研因子与未来收益的历史关系，不会修改风控规则。

自动晋升默认关闭。查看并人工晋升模型：

```bash
python3 -m src.cli model-status
python3 -m src.cli model-promote
```

只在模拟盘中允许通过验证门槛的模型自动晋升：

```bash
python3 -m src.cli paper AAPL MSFT NVDA --auto-promote-paper
```

也可导入已经按时间点构造、带前瞻收益标签的数据。字段和值域参见 [`examples/learning_observations_template.csv`](examples/learning_observations_template.csv)，特征为 `0~1`，`forward_return` 使用小数收益率（`0.05` 表示 `+5%`）：

```bash
python3 -m src.cli learn examples/learning_observations_template.csv
```

示例只有两行，用于说明格式，不足以训练模型。生产数据必须确保每个特征只使用该行 `timestamp` 当时已知的信息，避免未来数据泄漏。

### Binance 美股接入边界

代码通过 Binance Stocks `/sapi/v1/equity/*` 原生 SAPI 适配，不依赖 CCXT。先做只读连通性和标的检查：

```bash
export BINANCE_API_KEY='your-read-only-key'
python3 -m src.cli binance-preflight AAPL MSFT
```

#### 真实账户读取与实盘下单

读取余额/持仓/挂单以及下单都走**签名接口**，因此除 Key 之外必须配置 Secret（HMAC-SHA256 签名）。桌面端把两者分别存入 macOS 钥匙串，Python 侧只从环境变量读取：

```bash
export BINANCE_API_KEY='your-key'
export BINANCE_API_SECRET='your-secret'

# 首次必须签署美股免责声明，否则所有下单返回 486410
python3 -m src.desktop.cli --state-dir .berkshire-nexus live-accept-disclaimer

# 真实现金、持仓、挂单
python3 -m src.desktop.cli --state-dir .berkshire-nexus live-account

# 重启后先对账：核实每一笔本地记录订单的真实状态
python3 -m src.desktop.cli --state-dir .berkshire-nexus live-reconcile

# 预览（默认不下单）
python3 -m src.desktop.cli --state-dir .berkshire-nexus live-cycle AAPL MSFT

# 真实下单：三重放行缺一不可
export BERKSHIRE_NEXUS_LIVE_TRADING="我确认使用真实资金"
python3 -m src.desktop.cli --state-dir .berkshire-nexus live-cycle AAPL MSFT \
  --confirmation "我确认使用真实资金" --submit
```

**关于持仓来源**：Binance 没有 `/sapi/v1/equity/account` 这类持仓接口。成交后的股票以普通资产落在钱包里（默认 `CARD` 资金钱包，订单指定 `walletType=MAIN` 时落在现货钱包）。因此持仓由「钱包余额 ∩ 可交易股票池」还原，而不是累加成交历史——后者会漏掉 mint、划转和公司行为。

**关于订单状态**：`/order/place` 返回的 `status` 只是受理码（`S` 受理 / `F` 失败），**不等于成交**。受理后订单记为 `ACCEPTED`，真实成交量与均价一律由对账从交易所回读。POST 请求遇到网络错误时订单可能已到达交易所，此时记为 `UNKNOWN` 并留给对账处理，绝不自动重试。

所有订单都必须经过与模型隔离的确定性风控。默认规则包括：

- 单一标的持仓不超过组合的 10%；
- 每日总换手不超过组合的 25%；
- 当日亏损达到 1% 后停止新增风险；
- 实盘默认禁用市价单；
- 含预置、回退或推断数据的分析不能触发实盘买入；
- 实盘买入还要求价格是**券商权威**的——只有当 Binance 自己的行情接口确认了该价格，订单才放行，避免用第三方研究价格去打真实市场；
- 上一轮存在未解决订单时拒绝开新仓；
- 标的 `tradability` 为 `NONE`/单向时在发请求前就拦截；
- 风险开关触发后仍允许合法的减仓卖出。

Agent 自动循环仍然只走模拟盘——实盘每一次提交都必须是显式操作。

Binance Stocks 的账户资格、地区限制、PDT、交易时段和免责声明要求仍由 Binance 与当地法规决定。官方没有文档化的 Stocks 测试网，因此本项目把本地模拟盘作为上线前必经阶段。

### 2. 多股票横截面横向 PK 排序 (`compare`)

输入任意多只股票代码，框架会自动调用多因子模型与大师委员会进行综合打分与排序：

```bash
python3 -m src.cli compare TSM UBER APP ADBE SOFI
```

**运行结果输出**：
```text
╔════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
║                         🏆 BerkshireNexus Cross-Sectional Ranking & Comparison Board                       ║
╚════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝

Rank  Ticker   Company Name             Price (P/E)      Chokepoint      Masters      MoS (DCF)    Qlib Alpha   Total      Recommendation     
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
🥇 #1 UBER     Uber Technologies, Inc   $79.29 (17.4x)   L4 (8.50)       4.62/5.0     +16.9%       64.6         79.3       STRONG BUY        
🥈 #2 APP      AppLovin Corporation     $298.59 (22.9x)  L3 (6.97)       3.80/5.0     +48.7%       74.4         78.8       BUY (Satellite)   
🥉 #3 TSM      Taiwan Semiconductor     $205.00 (24.2x)  L5 (9.63)       4.52/5.0     -12.4%       74.2         77.8       BUY (Core Infra)  
   #4 ADBE     Adobe Inc.               $276.27 (15.8x)  L3 (7.61)       3.43/5.0     +15.1%       65.8         70.8       HOLD (Watchlist)  
   #5 SOFI     SoFi Technologies Inc    $18.24 (38.4x)   L1 (4.23)       2.45/5.0     -86.3%       37.8         34.8       AVOID / EXIT      
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
```

---

### 3. 单股票全维度透视决策备忘录 (`analyze`)

```bash
python3 -m src.cli analyze UBER
```

**输出示例**：
```text
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                  🎯 BerkshireNexus Executive Investment Memo: Uber Technologies, Inc.        ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
Ticker: UBER | Price: $79.29 | P/E: 17.4x | EPS: $4.56 | Beta: 1.16 | Sector: Internet / Mobility

┌── 📊 Multi-Framework Synthesis Scorecard ──────────────────────────────────────────────────┐
│ 1. Serenity Chokepoint (瓶颈) : Level 4/5 (8.5/10) - Global Mobility & Dispatch Network    │
│ 2. Berkshire 4 Masters (大师) : 4.62/5.0 - STRONG BUY                                      │
│ 3. Graham / DCF Valuation (估值) : MoS +16.9% (Intrinsic: $95.37) - Fairly Valued           │
│ 4. Qlib Multi-Factor Alpha (量化): 64.6/100 (Q:64.6 V:76.8 G:51.4 M:67.4)                  │
│ 5. Final BerkshireNexus Score: 79.3 / 100 ──► BUY / ACCUMULATE (Positive Asymmetry)        │
│ 6. Risk & Position Sizing    : Max Allocation 25.0% (Core Fortress Pillar)                 │
└────────────────────────────────────────────────────────────────────────────────────────────┘

🔍 段永平 5 句话镜子测试 (5-Sentence Mirror Test):
  • 1. Uber is the dominant global platform for moving people and food.
  • 2. Millions of drivers and riders create an insurmountable 2-sided network moat.
  • 3. The business has flipped into a $6B+ annual free cash flow machine.
  • 4. Autonomous vehicles need Uber's dispatch network to find paying riders.
  • 5. Trading at an attractive P/E (<18x) relative to its 15-20% compounding growth rate.

💀 查理·芒格 逆向思考 (Munger Inversion - 什么情况会让它死?):
  Tesla or Waymo successfully building an independent consumer ride-hailing app with zero commission...

🏛️ Investor Masters Boardroom Debate (6 大师视角对抗):
─────────────────────────────────────────────────────────────────────────────────────────────
  Warren Buffett     [Durable Moat & Owner Earnings  ] Score: 4.6 | Verdict: BUY
    Thesis: Uber operates the quintessential asset-light platform network. Dominant market share, pricing power, and FCF inflection ($6B+) at P/E under 18x.
    Concern: Potential platform transition risks if autonomous driving fleets bypass third-party dispatchers.
  Bill Ackman        [Activist Value & Compounder   ] Score: 4.9 | Verdict: STRONG BUY
    Thesis: Classic Ackman compounder: Dominant market share, high barriers to entry, pricing power, expanding advertising margin, and massive share buybacks.
    Concern: Wage inflation and local municipal regulations.
─────────────────────────────────────────────────────────────────────────────────────────────

🛑 Risk Manager Execution Mandate (风控执行红线):
  • 建议持仓上限: 25.0% | 动态止损线: -20.0%
  • 一票否决/离场触发条件:
    - Tesla Robotaxi vertical integration risk if Tesla scales standalone app successfully
    - Regulatory gig-worker classification and wage pressures
    - Quarterly Gross Margin dropping by >300 bps consecutively
```

---

## 📂 深度实战案例库 (Examples)

我们使用真实市场数据，对 5 大代表性风格资产进行了深度解剖，报告已完整归档在 `examples/` 目录下：

| 案例报告文件 | 核心标的 | 资产类型与定位 | 核心逻辑亮点 |
| :--- | :--- | :--- | :--- |
| [**01. 台积电深度研报**](examples/01_tsm_chokepoint_analysis.md) | `TSM` | **Level 5 唯一物理制造收费站** | 3nm/2nm >90% 绝对垄断，宁买 24x 代工也不追 45x 芯片设计 |
| [**02. 优步深度研报**](examples/02_uber_network_moat_analysis.md) | `UBER` | **双边网络垄断与 $60亿现金流** | 从烧钱到高盈利质变，自动驾驶时代不可替代的分发调度平台 |
| [**03. AppLovin 深度研报**](examples/03_applovin_high_beta_satellite.md) | `APP` | **AI 广告算法印钞机 (5%卫星仓)** | AXON 2.0 变现效率极高，但上游受制于苹果/谷歌，严格限仓 5% |
| [**04. Adobe 深度研报**](examples/04_adobe_value_trap_or_deep_value.md) | `ADBE` | **15.8x 深度价值 vs AI 颠覆** | 88% 极高毛利遭遇生成式 AI 冲击，价值陷阱与反转拐点的真实两难 |
| [**05. SoFi 深度研报**](examples/05_sofi_redline_disqualification.md) | `SOFI` | **伪科技概念一票否决出清** | 穿透包装故事，揭露 38x 估值买 7% 低 ROE 消费贷银行的巨大陷阱 |
| [**06. 全资产横截面配置指南**](examples/06_cross_sectional_benchmark.md) | `ALL` | **全天候投资组合构建策略** | 如何将大盘底座、物理收费站、现金流防线与高弹性奇兵科学组合 |

---

## 🛠️ 项目目录与模块划分

```text
berkshire-nexus/
├── SKILL.md                 # Claude Code / Codex / Cursor Agent Skill 协议定义
├── README.md                # 中文完整文档
├── README_EN.md             # 英文文档
├── pyproject.toml           # 现代 Python 封装配置
├── requirements.txt         # 无第三方运行时依赖
├── LICENSE                  # MIT 开源许可证
├── examples/                # 预置 6 篇机构级实战分析案例与资产看板
│   ├── 01_tsm_chokepoint_analysis.md
│   ├── 02_uber_network_moat_analysis.md
│   ├── 03_applovin_high_beta_satellite.md
│   ├── 04_adobe_value_trap_or_deep_value.md
│   ├── 05_sofi_redline_disqualification.md
│   ├── 06_cross_sectional_benchmark.md
│   └── learning_observations_template.csv # 外部学习数据格式示例
└── src/
    ├── __init__.py
    ├── cli.py               # analyze / compare / paper / learn / model / preflight
    ├── agent/
    │   └── cycle.py         # 一轮研究→学习→规划→风控→模拟执行
    ├── learning/
    │   ├── features.py      # 固定值域、可复现的特征抽取
    │   ├── model.py         # 线性收益模型与时间顺序验证
    │   ├── registry.py      # Champion / Challenger 模型注册表
    │   └── store.py         # 延迟标签和训练观察持久化
    ├── trading/
    │   ├── planner.py       # 目标仓位与再平衡意图
    │   ├── risk.py          # 与模型隔离的确定性风控
    │   ├── paper.py         # 持久化模拟券商
    │   ├── binance_stocks.py # Binance Stocks 原生 SAPI 适配
    │   └── types.py         # 订单、组合、成交契约
    ├── data/
    │   └── fetcher.py       # Yahoo 行情/历史 + Nasdaq 基本面路由、来源和回退追踪
    ├── research/
    │   ├── config.py        # 非秘密 Provider 设置与安全校验
    │   ├── news.py          # Yahoo / SEC EDGAR / Google 新闻事件、去重与证据 ID
    │   └── ai.py            # OpenAI-compatible / Ollama / Codex CLI 证据综合
    └── core/
        ├── chokepoint.py    # Serenity 供应链 5 级物理瓶颈与替代壁垒评分器
        ├── masters.py       # Berkshire 4 大师 + 对冲基金 6 视角对抗辩论系统
        ├── valuation.py     # Value-Investing-Agent 深度 DCF 与格雷厄姆内生价值
        ├── quant_factors.py # Qlib 微软多因子量化 Alpha 评分模型
        ├── risk_manager.py  # 仓位上限、波动率折价与逆向致死风控红线
        └── orchestrator.py  # 多智能体编排与决议备忘录生成器
```

---

## 💡 作为 Claude Code / Cursor / Codex Skill 安装

将本仓库作为 Agent Skill 直接引入你的开发环境中，随时在终端呼叫智能投研大脑：

```bash
# 复制到 Claude skills 目录
mkdir -p ~/.claude/skills/berkshire-nexus
cp SKILL.md ~/.claude/skills/berkshire-nexus/

# 在 Claude Code 中即可直接唤起
/berkshire-nexus analyze UBER
/berkshire-nexus compare TSM UBER APP ADBE SOFI
```

---

## 📜 免责声明 (Disclaimer)

*本项目（BerkshireNexus）仅供学术研究、AI 投资方法论探索及量化代码交流使用。本系统输出的任何分数、估值结果、大师辩论意见和持仓上限建议均不构成任何实质性的投资建议或证券买卖要约。模拟结果不代表未来表现；自动学习也不能消除模型风险、数据偏差、滑点、流动性或监管风险。金融市场有风险，投资需独立思考与严谨决策。*

### 本机签名（避免钥匙串反复弹窗）

Tauri 默认 ad-hoc 签名，**每次构建签名身份都不同**，macOS 因此把每次重建当作全新程序，
之前授予的钥匙串访问权限全部作废 —— 表现就是每次更新 app 都要重新授权好几次。

`tauri.conf.json` 已配置 `bundle.macOS.signingIdentity = "BerkshireNexus Local Signing"`。
换机器或重装系统后需要重新创建这个自签名证书：

```bash
# 1. 生成证书
cat > /tmp/bn-cert.cnf <<'CNF'
[ req ]
default_md = sha256
prompt = no
distinguished_name = dn
x509_extensions = v3
[ dn ]
CN = BerkshireNexus Local Signing
[ v3 ]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
subjectKeyIdentifier = hash
CNF
openssl req -new -x509 -newkey rsa:2048 -nodes -days 3650 \
  -config /tmp/bn-cert.cnf -keyout /tmp/bn-key.pem -out /tmp/bn-cert.pem
openssl pkcs12 -export -inkey /tmp/bn-key.pem -in /tmp/bn-cert.pem \
  -name "BerkshireNexus Local Signing" -out /tmp/bn.p12 -passout pass:bnlocal

# 2. 导入登录钥匙串
security import /tmp/bn.p12 -k ~/Library/Keychains/login.keychain-db \
  -P bnlocal -T /usr/bin/codesign -T /usr/bin/security

# 3. 设为受信任（需要输入登录密码）
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain /tmp/bn-cert.pem

# 4. 确认可用
security find-identity -v -p codesigning   # 应列出 BerkshireNexus Local Signing
rm -f /tmp/bn-key.pem /tmp/bn.p12          # 私钥已在钥匙串，删掉临时文件
```

这是**自签名**证书，只解决本机重复授权问题；对外分发仍需 Apple Developer ID 签名与公证。
