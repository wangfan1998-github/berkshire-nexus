import {
  Activity,
  Archive,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bot,
  BrainCircuit,
  Check,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  ClipboardList,
  FlaskConical,
  Gauge,
  Database,
  KeyRound,
  LayoutDashboard,
  LineChart,
  LoaderCircle,
  LockKeyhole,
  Pause,
  Play,
  RefreshCw,
  Save,
  Search,
  Settings as SettingsIcon,
  ShieldCheck,
  Sparkles,
  Square,
  Trash2,
  TrendingUp,
  WalletCards,
  X,
  Zap,
} from "lucide-react";
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { desktopBridge } from "./bridge";
import { defaultSettings } from "./mock";
import { LIVE_ACKNOWLEDGEMENT } from "./types";
import type {
  AnalysisReport,
  AppSnapshot,
  CredentialCheck,
  DesktopSettings,
  Execution,
  LiveAccount,
  LiveCycleResult,
  PageId,
  RiskConfig,
} from "./types";

type BusyAction =
  | "boot"
  | "refresh"
  | "research"
  | "cycle"
  | "agent"
  | "save"
  | "key"
  | "ai-key"
  | "ai-test"
  | "preflight"
  | "promote"
  | "secret"
  | "verify"
  | "live-account"
  | "reconcile"
  | "disclaimer"
  | "live-preview"
  | "live-submit"
  | null;

type Toast = { id: number; tone: "success" | "error" | "info"; message: string };

const navItems: Array<{ id: PageId; label: string; description: string; icon: typeof Activity }> = [
  { id: "overview", label: "总览", description: "今日运行面", icon: LayoutDashboard },
  { id: "research", label: "研究", description: "证据与裁决", icon: Search },
  { id: "ai", label: "AI 投研", description: "模型与数据源", icon: BrainCircuit },
  { id: "portfolio", label: "组合", description: "模拟资产", icon: WalletCards },
  { id: "live", label: "实盘", description: "真实账户与下单", icon: Zap },
  { id: "agent", label: "Agent", description: "循环与任务", icon: Bot },
  { id: "models", label: "策略学习", description: "Champion / Challenger", icon: FlaskConical },
  { id: "risk", label: "风控", description: "确定性边界", icon: ShieldCheck },
  { id: "audit", label: "审计", description: "不可变轨迹", icon: ClipboardList },
  { id: "settings", label: "设置", description: "Binance 与系统", icon: SettingsIcon },
];

const pageMeta: Record<PageId, { eyebrow: string; title: string; intro: string }> = {
  overview: { eyebrow: "OPERATIONS / TODAY", title: "交易研究台", intro: "从证据到模拟成交，观察每一项判断如何穿过风控边界。" },
  research: { eyebrow: "RESEARCH / EVIDENCE", title: "股票研究", intro: "并行检验瓶颈、商业质量、估值、量化因子与失败条件。" },
  ai: { eyebrow: "INTELLIGENCE / PROVIDERS", title: "AI 投研配置", intro: "把最新行情、新闻证据与可配置模型接入同一条可审计研究链。" },
  portfolio: { eyebrow: "PAPER BOOK / CAPITAL", title: "模拟组合", intro: "资本、持仓和成交使用同一套可追溯账本。" },
  live: { eyebrow: "LIVE / REAL MONEY", title: "实盘账户与执行", intro: "从 Binance 读取真实现金与持仓；下单需要 Secret 与确认短语双重放行。" },
  agent: { eyebrow: "AUTOMATION / PAPER", title: "Agent 运行台", intro: "启动有界的研究—风控—模拟成交循环，可在系统托盘持续运行。" },
  models: { eyebrow: "LEARNING / REGISTRY", title: "策略学习", intro: "Champion / Challenger 只学习收益映射；它不是生成研究文本的大模型。" },
  risk: { eyebrow: "RISK / DETERMINISTIC", title: "风控边界", intro: "这些规则独立于模型，并且桌面端只能收紧默认安全阈值。" },
  audit: { eyebrow: "AUDIT / LEDGER", title: "审计日志", intro: "每轮分析、订单意图、风控决定和模拟成交都写入独立记录。" },
  settings: { eyebrow: "SYSTEM / CONNECTIONS", title: "系统设置", intro: "API Key 只写入 macOS 钥匙串，不进入配置文件、前端状态或日志。" },
};

const money = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const compactMoney = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });

function formatDate(value?: string | null, includeTime = true) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
  }).format(date);
}

function cnRecommendation(value: string) {
  const normalized = value.toUpperCase();
  if (normalized.includes("STRONG BUY")) return "强力买入";
  if (normalized.includes("BUY")) return "买入观察";
  if (normalized.includes("SELL") || normalized.includes("AVOID")) return "回避 / 卖出";
  return "持有观察";
}

function stateLabel(state?: string) {
  const labels: Record<string, string> = {
    stopped: "已停止",
    running_cycle: "正在执行一轮",
    waiting: "等待下一轮",
    error_waiting: "异常后等待",
    running: "运行中",
  };
  return labels[state ?? ""] ?? state ?? "未知";
}

function asError(error: unknown) {
  if (error instanceof Error) return error.message;
  return String(error);
}

function SectionHeading({
  index,
  title,
  note,
  action,
}: {
  index?: string;
  title: string;
  note?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div className="section-heading-copy">
        {index && <span className="section-index">{index}</span>}
        <div>
          <h2>{title}</h2>
          {note && <p>{note}</p>}
        </div>
      </div>
      {action && <div className="section-action">{action}</div>}
    </div>
  );
}

function StatusMark({ tone = "neutral", children }: { tone?: "good" | "warn" | "risk" | "neutral"; children: ReactNode }) {
  return <span className={`status-mark status-${tone}`}><span aria-hidden="true" />{children}</span>;
}

function EmptyState({ icon: Icon = Archive, title, body }: { icon?: typeof Archive; title: string; body: string }) {
  return (
    <div className="empty-state">
      <Icon size={22} aria-hidden="true" />
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function LoadingPage() {
  return (
    <div className="loading-page" aria-label="正在读取本地状态" aria-busy="true">
      <div className="loading-rule" />
      <div className="loading-rule short" />
      <div className="loading-block" />
      <div className="loading-block small" />
    </div>
  );
}

function Metric({ label, value, detail, tone }: { label: string; value: ReactNode; detail: ReactNode; tone?: "good" | "risk" }) {
  return (
    <div className={`metric ${tone ? `metric-${tone}` : ""}`}>
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      <span className="metric-detail">{detail}</span>
    </div>
  );
}

function ExecutionRows({ values }: { values: Execution[] }) {
  if (!values.length) {
    return <EmptyState title="还没有模拟成交" body="运行一次 Paper 周期后，成交会按时间倒序出现在这里。" />;
  }
  return (
    <div className="ledger-table execution-ledger" role="table" aria-label="模拟成交">
      <div className="ledger-row ledger-head" role="row">
        <span role="columnheader">时间</span>
        <span role="columnheader">标的</span>
        <span role="columnheader">方向</span>
        <span role="columnheader">数量</span>
        <span role="columnheader">均价</span>
        <span role="columnheader">状态</span>
      </div>
      {values.map((execution, index) => (
        <div className="ledger-row" role="row" key={`${execution.recorded_at_utc}-${execution.ticker}-${index}`}>
          <span className="mono muted" role="cell">{formatDate(execution.recorded_at_utc)}</span>
          <strong className="mono" role="cell">{execution.ticker}</strong>
          <span role="cell" className={`trade-side side-${execution.side.toLowerCase()}`}>
            {execution.side === "BUY" ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {execution.side === "BUY" ? "买入" : "卖出"}
          </span>
          <span className="mono" role="cell">{number.format(execution.filled_quantity)}</span>
          <span className="mono" role="cell">{money.format(execution.average_price)}</span>
          <StatusMark tone={execution.status === "FILLED" ? "good" : "warn"}>{execution.status}</StatusMark>
        </div>
      ))}
    </div>
  );
}

function Overview({ snapshot, goTo }: { snapshot: AppSnapshot; goTo: (page: PageId) => void }) {
  const dayChange = snapshot.portfolio.equity - snapshot.portfolio.start_of_day_equity;
  const dayPct = snapshot.portfolio.start_of_day_equity
    ? dayChange / snapshot.portfolio.start_of_day_equity * 100
    : 0;
  const trained = snapshot.learning.observation_count >= snapshot.learning.minimum_training_samples;
  const analyses = snapshot.last_cycle?.analyses ?? [];

  return (
    <div className="page-stack overview-page">
      <section className="overview-strip" aria-label="组合概览">
        <Metric label="模拟净值" value={money.format(snapshot.portfolio.equity)} detail={`${snapshot.portfolio.holdings.length} 个持仓`} />
        <Metric
          label="今日变化"
          value={`${dayChange >= 0 ? "+" : ""}${money.format(dayChange)}`}
          detail={`${dayPct >= 0 ? "+" : ""}${dayPct.toFixed(2)}%`}
          tone={dayChange >= 0 ? "good" : "risk"}
        />
        <Metric label="可用现金" value={money.format(snapshot.portfolio.cash)} detail={`${(snapshot.portfolio.cash / Math.max(snapshot.portfolio.equity, 1) * 100).toFixed(1)}% 现金`} />
        <Metric label="今日换手" value={compactMoney.format(snapshot.portfolio.daily_traded_notional)} detail={`上限 ${snapshot.risk.max_daily_turnover_pct}%`} />
      </section>

      <section className="evidence-chain">
        <SectionHeading index="01" title="证据链状态" note="每一步必须留下可解释产物，学习模型不能绕过风控。" />
        <div className="chain-track">
          <button className="chain-node" onClick={() => goTo("research")}>
            <span>研究</span>
            <strong>{analyses.length ? `${analyses.length} 个标的` : "等待首轮"}</strong>
            <small>{formatDate(snapshot.last_cycle?.generated_at_utc)}</small>
          </button>
          <ArrowRight className="chain-arrow" size={18} aria-hidden="true" />
          <button className="chain-node" onClick={() => goTo("risk")}>
            <span>风控</span>
            <strong>{snapshot.risk.minimum_analysis_score}+ 分</strong>
            <small>规则独立锁定</small>
          </button>
          <ArrowRight className="chain-arrow" size={18} aria-hidden="true" />
          <button className="chain-node" onClick={() => goTo("portfolio")}>
            <span>模拟成交</span>
            <strong>{snapshot.executions.length} 条记录</strong>
            <small>Paper only</small>
          </button>
          <ArrowRight className="chain-arrow" size={18} aria-hidden="true" />
          <button className="chain-node" onClick={() => goTo("models")}>
            <span>学习反馈</span>
            <strong>{snapshot.learning.observation_count} / {snapshot.learning.minimum_training_samples}</strong>
            <small>{trained ? "训练门槛已满足" : "继续积累标签"}</small>
          </button>
        </div>
      </section>

      <div className="two-column wide-left">
        <section className="ruled-section">
          <SectionHeading
            index="02"
            title="最近研究裁决"
            note="按确定性综合分排序；网络研究数据和回退数据都不是 Binance 权威执行数据。"
            action={<button className="text-button" onClick={() => goTo("research")}>展开研究 <ChevronRight size={14} /></button>}
          />
          {analyses.length ? (
            <div className="research-lines">
              {analyses.map((item, index) => (
                <div className="research-line" key={item.ticker}>
                  <span className="rank mono">{String(index + 1).padStart(2, "0")}</span>
                  <strong className="ticker mono">{item.ticker}</strong>
                  <div className="score-rule" aria-label={`综合评分 ${item.score.toFixed(1)}`}>
                    <span style={{ width: `${Math.min(item.score, 100)}%` }} />
                  </div>
                  <strong className="mono score-value">{item.score.toFixed(1)}</strong>
                  <span className="recommendation">{cnRecommendation(item.recommendation)}</span>
                  <StatusMark tone={item.uses_fallback_data ? "warn" : "good"}>{item.uses_fallback_data ? "回退数据" : "网络完整"}</StatusMark>
                </div>
              ))}
            </div>
          ) : <EmptyState icon={Search} title="还没有研究结果" body="前往 Agent 运行一轮，或在研究页手动分析股票池。" />}
        </section>

        <aside className="operator-notes">
          <SectionHeading index="03" title="运行注记" />
          <div className="note-entry">
            <span className={`activity-dot ${snapshot.agent.running ? "active" : ""}`} />
            <div><strong>Agent {snapshot.agent.running ? "正在运行" : "当前停止"}</strong><p>{stateLabel(snapshot.agent.state)} · 已完成 {snapshot.agent.cycles_completed} 轮</p></div>
          </div>
          <div className="note-entry">
            <span className={`activity-dot ${snapshot.learning.champion ? "active" : ""}`} />
            <div><strong>{snapshot.learning.champion ? "Champion 已登记" : "等待首个模型"}</strong><p>{snapshot.learning.champion?.version ?? "样本达标后训练 Challenger"}</p></div>
          </div>
          <div className="note-entry risk-note">
            <LockKeyhole size={16} />
            <div><strong>实盘保持锁定</strong><p>缺少权威账户快照、重启恢复与订单对账。</p></div>
          </div>
        </aside>
      </div>

      <section className="ruled-section">
        <SectionHeading index="04" title="最近模拟成交" action={<button className="text-button" onClick={() => goTo("portfolio")}>查看账本 <ChevronRight size={14} /></button>} />
        <ExecutionRows values={snapshot.executions.slice(0, 5)} />
      </section>
    </div>
  );
}

function Research({
  settings,
  reports,
  selectedTicker,
  busy,
  onAnalyze,
  onSelect,
}: {
  settings: DesktopSettings;
  reports: AnalysisReport[];
  selectedTicker: string | null;
  busy: boolean;
  onAnalyze: (tickers: string[]) => Promise<void>;
  onSelect: (ticker: string) => void;
}) {
  const [query, setQuery] = useState(settings.universe.join(" "));
  const report = reports.find((value) => value.ticker === selectedTicker) ?? reports[0];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const values = query.split(/[\s,，]+/).map((value) => value.trim().toUpperCase()).filter(Boolean);
    if (values.length) void onAnalyze(Array.from(new Set(values)));
  };

  return (
    <div className="page-stack research-page">
      <form className="research-command" onSubmit={submit}>
        <label htmlFor="research-tickers">股票代码</label>
        <div className="command-input">
          <Search size={18} aria-hidden="true" />
          <input id="research-tickers" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="AAPL MSFT NVDA" autoComplete="off" />
          <button className="primary-button" type="submit" disabled={busy || !query.trim()}>
            {busy ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}
            {busy ? "正在汇总证据" : "开始研究"}
          </button>
        </div>
        <p>默认读取 Yahoo 最新可用行情、Nasdaq 基本面与当前新闻。每项证据都会显示来源、时间和降级状态。</p>
      </form>

      {!reports.length ? (
        <EmptyState icon={LineChart} title="等待研究任务" body="输入一个或多个美股代码。框架会同时生成瓶颈、价值大师、DCF、多因子与风险结论。" />
      ) : (
        <>
          <div className="report-tabs" role="tablist" aria-label="研究标的">
            {reports.map((item, index) => (
              <button
                role="tab"
                aria-selected={report?.ticker === item.ticker}
                className={report?.ticker === item.ticker ? "active" : ""}
                onClick={() => onSelect(item.ticker)}
                key={item.ticker}
              >
                <span className="mono tab-index">{String(index + 1).padStart(2, "0")}</span>
                <strong className="mono">{item.ticker}</strong>
                <span className="mono">{item.score.toFixed(1)}</span>
              </button>
            ))}
          </div>

          {report && <ResearchMemo report={report} />}
        </>
      )}
    </div>
  );
}

function verificationLabel(report: AnalysisReport) {
  if (report.verification_level === "third-party-complete") return "第三方研究数据完整";
  if (report.verification_level === "third-party-degraded") return "部分字段已降级";
  return "离线回退数据";
}

function aiBias(value: AnalysisReport["ai_research"]["action_bias"]) {
  return ({ BULLISH: "偏多", NEUTRAL: "中性", BEARISH: "偏空", INSUFFICIENT_EVIDENCE: "证据不足" } as const)[value];
}

function ResearchMemo({ report }: { report: AnalysisReport }) {
  const factors = [
    ["质量", report.quant.quality_score],
    ["价值", report.quant.value_score],
    ["增长", report.quant.growth_score],
    ["动量", report.quant.momentum_score],
    ["风险调整", report.quant.risk_adjusted_score],
  ] as const;

  return (
    <article className="investment-memo">
      <header className="memo-header">
        <div>
          <span className="mono memo-code">{report.ticker} / {report.sector}</span>
          <h2>{report.name}</h2>
          <div className="memo-source">
            <StatusMark tone={report.verification_level === "third-party-complete" ? "good" : "warn"}>{verificationLabel(report)}</StatusMark>
            <span className="mono">{report.data_source}</span>
            <span className="mono">行情 {formatDate(report.quote_as_of_utc)}</span>
          </div>
        </div>
        <div className="memo-verdict">
          <span>综合裁决</span>
          <strong className="mono">{report.score.toFixed(1)}</strong>
          <b>{cnRecommendation(report.recommendation)}</b>
        </div>
      </header>

      <div className="memo-measures">
        <Metric label="最新可用价" value={money.format(report.price)} detail={`${report.price_change_pct >= 0 ? "+" : ""}${report.price_change_pct.toFixed(2)}% · ${report.market_status === "OPEN" ? "交易中" : "已收盘"}`} tone={report.price_change_pct >= 0 ? "good" : "risk"} />
        <Metric label="物理瓶颈" value={`L${report.chokepoint.chokepoint_level}`} detail={`${report.chokepoint.overall_score.toFixed(1)} / 10`} />
        <Metric label="DCF 内在价值" value={money.format(report.valuation.intrinsic_value_dcf)} detail={`${report.valuation.margin_of_safety_pct >= 0 ? "+" : ""}${report.valuation.margin_of_safety_pct.toFixed(1)}% 安全边际`} />
        <Metric label="建议上限" value={`${report.risk.recommended_max_allocation_pct.toFixed(1)}%`} detail={`Beta ${report.beta.toFixed(2)}`} />
      </div>

      <div className="memo-body two-column equal">
        <section className="ruled-section">
          <SectionHeading index="A" title="商业证据与逆向检验" />
          <div className="thesis-callout">
            <span>瓶颈命题</span>
            <strong>{report.chokepoint.chokepoint_title}</strong>
          </div>
          <div className="prose-entry">
            <span>镜子测试</span>
            <p>{report.masters.mirror_test_summary}</p>
          </div>
          <div className="prose-entry risk-prose">
            <span>芒格逆向</span>
            <p>{report.masters.munger_inversion_summary}</p>
          </div>
        </section>

        <section className="ruled-section factor-section">
          <SectionHeading index="B" title="多因子剖面" note="仅作为可学习信号，不直接拥有下单权限。" />
          <div className="factor-list">
            {factors.map(([label, value]) => (
              <div className="factor-row" key={label}>
                <span>{label}</span>
                <div><i style={{ width: `${Math.max(0, Math.min(value, 100))}%` }} /></div>
                <strong className="mono">{value.toFixed(1)}</strong>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="ruled-section evidence-section">
        <SectionHeading index="C" title="数据来源与新鲜度" note="研究级第三方数据不等于 Binance 券商账户权威数据，因此不能触发 Live 买单。" />
        <div className="source-ledger">
          {report.source_trace.map((source) => (
            <div className="source-row" key={`${source.provider}-${source.kind}`}>
              <Database size={15} />
              <div><strong>{source.provider}</strong><span>{source.kind}</span></div>
              <span className="mono">{source.as_of_utc ? formatDate(source.as_of_utc) : `${source.latency_ms} ms`}</span>
              <StatusMark tone={source.status === "ok" ? "good" : "risk"}>{source.status === "ok" ? "成功" : "失败"}</StatusMark>
            </div>
          ))}
        </div>
        <div className="freshness-notes">
          <span>行情时间 <strong className="mono">{formatDate(report.quote_as_of_utc)}</strong></span>
          <span>基本面期末 <strong className="mono">{report.fundamentals_as_of || "未返回"}</strong></span>
          <span>交易所 <strong className="mono">{report.exchange || "未知"}</strong></span>
          <span>实盘权威 <strong className="mono risk-text">否</strong></span>
        </div>
        {!!report.fallback_fields.length && <div className="inline-error"><CircleAlert size={16} /><span><strong>回退字段</strong>{report.fallback_fields.join("、")}</span></div>}
      </section>

      <div className="memo-body two-column evidence-columns">
        <section className="ruled-section news-section">
          <SectionHeading index="D" title="最新新闻与事件证据" note={`${report.news.providers_attempted.join(" + ") || "新闻检索未启用"} · ${report.news.latency_ms} ms`} />
          {report.news.items.length ? (
            <div className="news-ledger">
              {report.news.items.map((item) => (
                <a href={item.url} target="_blank" rel="noreferrer" key={item.evidence_id}>
                  <span className="evidence-id mono">{item.evidence_id}</span>
                  <div><strong>{item.title}</strong><span>{item.publisher} · {formatDate(item.published_at_utc)}</span></div>
                  <ArrowUpRight size={14} />
                </a>
              ))}
            </div>
          ) : <EmptyState icon={Archive} title={report.news.status === "disabled" ? "新闻检索未启用" : "没有拿到当前新闻"} body={report.news.error ?? "本次检索没有返回与标的直接相关的可引用标题。"} />}
          {report.news.error && report.news.items.length > 0 && <div className="provider-warning"><CircleAlert size={14} />部分新闻源降级：{report.news.error}</div>}
        </section>

        <section className="ruled-section ai-research-section">
          <SectionHeading index="E" title="AI 证据综合" note={report.ai_research.status === "ok" ? `${report.ai_research.provider} / ${report.ai_research.model} · ${report.ai_research.latency_ms} ms` : "AI 不参与确定性分数与风控"} />
          {report.ai_research.status === "ok" ? (
            <div className="ai-synthesis">
              <div className="ai-verdict"><StatusMark tone={report.ai_research.action_bias === "BULLISH" ? "good" : report.ai_research.action_bias === "BEARISH" ? "risk" : "warn"}>{aiBias(report.ai_research.action_bias)}</StatusMark><span className="mono">置信度 {(report.ai_research.confidence * 100).toFixed(0)}%</span></div>
              <p>{report.ai_research.summary}</p>
              <div className="thesis-callout"><span>可证伪命题</span><strong>{report.ai_research.thesis}</strong></div>
              <div className="ai-points"><div><span>催化</span><ul>{report.ai_research.catalysts.map((item) => <li key={item}>{item}</li>)}</ul></div><div><span>风险</span><ul>{report.ai_research.risks.map((item) => <li key={item}>{item}</li>)}</ul></div></div>
              <div className="citation-row"><span>引用</span>{report.ai_research.citations.length ? report.ai_research.citations.map((item) => <b className="mono" key={item}>{item}</b>) : <em>未引用当前新闻，置信度已受限</em>}</div>
            </div>
          ) : (
            <EmptyState icon={BrainCircuit} title={report.ai_research.status === "disabled" ? "AI 研究尚未启用" : "AI Provider 本轮失败"} body={report.ai_research.error ?? "前往 AI 投研页选择 OpenAI-compatible、Ollama 或本地 Codex。即使关闭 AI，实时数据和新闻仍可独立工作。"} />
          )}
        </section>
      </div>

      <section className="redline-section">
        <SectionHeading index="F" title="论文失效红线" note={`组合角色：${report.risk.portfolio_role} · 建议止损触发 ${report.risk.stop_loss_trigger_pct.toFixed(1)}%`} />
        <ol>
          {report.risk.redline_failure_criteria.map((criterion) => <li key={criterion}>{criterion}</li>)}
        </ol>
      </section>
    </article>
  );
}

function Portfolio({ snapshot }: { snapshot: AppSnapshot }) {
  const investedPct = snapshot.portfolio.equity
    ? snapshot.portfolio.holdings_value / snapshot.portfolio.equity * 100
    : 0;
  return (
    <div className="page-stack">
      <section className="capital-ledger">
        <div className="capital-total">
          <span>Paper 组合权益</span>
          <strong className="mono">{money.format(snapshot.portfolio.equity)}</strong>
          <p>交易日 {snapshot.portfolio.trading_date || "尚未开始"} · 数据保存在本机应用目录</p>
        </div>
        <div className="capital-composition" aria-label="组合资金构成">
          <div className="composition-bar"><span style={{ width: `${investedPct}%` }} /></div>
          <div className="composition-labels">
            <span><i className="invested" />持仓 {money.format(snapshot.portfolio.holdings_value)} · {investedPct.toFixed(1)}%</span>
            <span><i />现金 {money.format(snapshot.portfolio.cash)} · {(100 - investedPct).toFixed(1)}%</span>
          </div>
        </div>
      </section>

      <section className="ruled-section">
        <SectionHeading index="01" title="持仓账本" note="价格来自最近一次研究周期；这是本地模拟账户，不代表 Binance 真实持仓。" />
        {snapshot.portfolio.holdings.length ? (
          <div className="ledger-table holdings-ledger" role="table" aria-label="模拟持仓">
            <div className="ledger-row ledger-head" role="row">
              <span role="columnheader">标的</span><span role="columnheader">数量</span><span role="columnheader">参考价</span><span role="columnheader">市值</span><span role="columnheader">权重</span><span role="columnheader">风控余量</span>
            </div>
            {snapshot.portfolio.holdings.map((holding) => {
              const capacity = Math.max(0, snapshot.risk.max_position_pct - holding.weight_pct);
              return (
                <div className="ledger-row" role="row" key={holding.ticker}>
                  <strong className="mono" role="cell">{holding.ticker}</strong>
                  <span className="mono" role="cell">{number.format(holding.quantity)}</span>
                  <span className="mono" role="cell">{money.format(holding.price)}</span>
                  <span className="mono" role="cell">{money.format(holding.market_value)}</span>
                  <span className="mono" role="cell">{holding.weight_pct.toFixed(2)}%</span>
                  <span role="cell" className={capacity < 1 ? "risk-text" : "muted"}>{capacity.toFixed(2)}% 可用</span>
                </div>
              );
            })}
          </div>
        ) : <EmptyState title="当前全部为现金" body="Agent 尚未产生通过风控的模拟买入。" />}
      </section>

      <section className="ruled-section">
        <SectionHeading index="02" title="成交历史" note="仅追加记录；手续费、拒单与失败原因也会进入审计。" />
        <ExecutionRows values={snapshot.executions} />
      </section>
    </div>
  );
}

function AgentPage({
  snapshot,
  settings,
  running,
  busy,
  onSettings,
  onStart,
  onStop,
  onCycle,
}: {
  snapshot: AppSnapshot;
  settings: DesktopSettings;
  running: boolean;
  busy: boolean;
  onSettings: (next: DesktopSettings) => void;
  onStart: () => Promise<void>;
  onStop: () => Promise<void>;
  onCycle: () => Promise<void>;
}) {
  const updateUniverse = (raw: string) => onSettings({
    ...settings,
    universe: Array.from(new Set(raw.split(/[\s,，]+/).map((value) => value.trim().toUpperCase()).filter(Boolean))),
  });

  return (
    <div className="page-stack agent-page">
      <section className={`agent-console ${running ? "agent-live" : ""}`}>
        <div className="agent-orbit" aria-hidden="true"><span /><span /><Bot size={28} /></div>
        <div className="agent-console-copy">
          <span className="mono console-label">PAPER AGENT / {running ? "ACTIVE" : "STANDBY"}</span>
          <h2>{running ? "循环正在后台运行" : "Agent 已就绪，等待启动"}</h2>
          <p>{running ? `当前状态：${snapshot.agent.state === "stopped" ? "启动中" : stateLabel(snapshot.agent.state)}。关闭窗口后会留在系统托盘。` : "启动后立即执行第一轮，再按设定间隔持续研究、风控与模拟成交。"}</p>
          <div className="console-facts">
            <span><Activity size={14} />{snapshot.agent.cycles_completed} 轮已完成</span>
            <span><Gauge size={14} />每 {settings.interval_minutes} 分钟</span>
            <span><Archive size={14} />{snapshot.audits.length} 份审计</span>
          </div>
        </div>
        <div className="agent-controls">
          {running ? (
            <button className="danger-button" onClick={() => void onStop()} disabled={busy}><Square size={15} fill="currentColor" />停止 Agent</button>
          ) : (
            <button className="primary-button large" onClick={() => void onStart()} disabled={busy || !settings.universe.length}>
              {busy ? <LoaderCircle className="spin" size={17} /> : <Play size={17} fill="currentColor" />}启动 Paper Agent
            </button>
          )}
          <button className="secondary-button" onClick={() => void onCycle()} disabled={busy || running || !settings.universe.length}>
            <RefreshCw className={busy ? "spin" : ""} size={15} />只运行一轮
          </button>
        </div>
      </section>

      <div className="two-column equal agent-settings-grid">
        <section className="ruled-section form-section">
          <SectionHeading index="01" title="运行参数" note="保存后用于手动周期与后台循环。" />
          <label className="field-label">
            <span>股票池 <small>{settings.universe.length} 个标的</small></span>
            <input value={settings.universe.join(" ")} onChange={(event) => updateUniverse(event.target.value)} disabled={running} spellCheck={false} />
          </label>
          <div className="inline-fields">
            <label className="field-label">
              <span>循环间隔 <small>分钟</small></span>
              <input type="number" min="1" max="1440" value={settings.interval_minutes} disabled={running} onChange={(event) => onSettings({ ...settings, interval_minutes: Number(event.target.value) })} />
            </label>
            <label className="field-label">
              <span>初始模拟资金 <small>USD</small></span>
              <input type="number" min="1000" step="1000" value={settings.initial_cash} disabled={running} onChange={(event) => onSettings({ ...settings, initial_cash: Number(event.target.value) })} />
            </label>
          </div>
          <label className="switch-row">
            <span><strong>自动晋升模型</strong><small>仅允许通过验证门槛的 Challenger 在模拟盘晋升</small></span>
            <input type="checkbox" checked={settings.auto_promote_paper} disabled={running} onChange={(event) => onSettings({ ...settings, auto_promote_paper: event.target.checked })} />
            <i aria-hidden="true" />
          </label>
        </section>

        <section className="ruled-section">
          <SectionHeading index="02" title="当前周期状态" />
          <dl className="definition-ledger">
            <div><dt>进程状态</dt><dd><StatusMark tone={running ? "good" : "neutral"}>{running ? "运行中" : "已停止"}</StatusMark></dd></div>
            <div><dt>最后周期</dt><dd className="mono">{formatDate(snapshot.agent.last_cycle_at_utc)}</dd></div>
            <div><dt>最近模型</dt><dd className="mono truncate">{snapshot.learning.champion?.version ?? "尚无 Champion"}</dd></div>
            <div><dt>实盘权限</dt><dd><StatusMark tone="risk">锁定</StatusMark></dd></div>
          </dl>
          {snapshot.agent.last_error && (
            <div className="inline-error"><CircleAlert size={16} /><span><strong>最近错误</strong>{snapshot.agent.last_error}</span></div>
          )}
          <div className="safety-footnote"><LockKeyhole size={16} /><p>后台 Agent 只使用本地 Paper Broker。即使已经保存 Binance API Key，也不会提交真实订单。</p></div>
        </section>
      </div>
    </div>
  );
}

function AISettingsPage({
  settings,
  configured,
  busy,
  onSettings,
  onSaveSettings,
  onSaveKey,
  onDeleteKey,
  onTest,
}: {
  settings: DesktopSettings;
  configured: boolean;
  busy: BusyAction;
  onSettings: (next: DesktopSettings) => void;
  onSaveSettings: () => Promise<void>;
  onSaveKey: (key: string) => Promise<void>;
  onDeleteKey: () => Promise<void>;
  onTest: () => Promise<void>;
}) {
  const [key, setKey] = useState("");
  const research = settings.research;
  const update = (patch: Partial<DesktopSettings["research"]>) => onSettings({
    ...settings,
    research: { ...research, ...patch },
  });
  const selectProvider = (provider: DesktopSettings["research"]["ai_provider"]) => {
    const presets = {
      "openai-compatible": { ai_base_url: "https://api.openai.com/v1", ai_model: "gpt-5-mini" },
      ollama: { ai_base_url: "http://127.0.0.1:11434", ai_model: "qwen3:8b" },
      "codex-cli": { ai_base_url: "local://codex", ai_model: "gpt-5.6-sol" },
    } as const;
    update({ ai_provider: provider, ...presets[provider] });
  };
  const requiresKey = research.ai_provider === "openai-compatible";
  const submitKey = (event: FormEvent) => {
    event.preventDefault();
    void onSaveKey(key).then(() => setKey("")).catch(() => undefined);
  };

  return (
    <div className="page-stack ai-settings-page">
      <section className="connection-status ai-connection-status">
        <div className={`connection-emblem ${research.ai_enabled ? "connected" : ""}`}><BrainCircuit size={25} /></div>
        <div><span className="mono">RESEARCH INTELLIGENCE / OPTIONAL</span><h2>{research.ai_enabled ? `${research.ai_provider} · ${research.ai_model}` : "AI 证据综合当前关闭"}</h2><p>行情和新闻始终独立获取；大模型只综合现有证据，不改写分数、风控或执行权限。</p></div>
        <StatusMark tone={research.ai_enabled ? "good" : "warn"}>{research.ai_enabled ? "已启用" : "未启用"}</StatusMark>
      </section>

      <div className="two-column equal ai-config-grid">
        <section className="ruled-section form-section provider-form">
          <SectionHeading index="01" title="模型 Provider" note="支持 OpenAI-compatible、Ollama 和本机 Codex CLI。" />
          <label className="toggle-row wide-toggle">
            <span><strong>启用 AI 研究综合</strong><small>每个标的会产生一次模型请求；可能产生 API 或 Codex 用量。</small></span>
            <input type="checkbox" checked={research.ai_enabled} onChange={(event) => update({ ai_enabled: event.target.checked })} />
          </label>
          <div className="form-grid">
            <label className="field-label"><span>Provider</span><select value={research.ai_provider} onChange={(event) => selectProvider(event.target.value as DesktopSettings["research"]["ai_provider"])}><option value="openai-compatible">OpenAI-compatible API</option><option value="ollama">Ollama（本机）</option><option value="codex-cli">Codex CLI（本机登录）</option></select></label>
            <label className="field-label"><span>Model ID</span><input value={research.ai_model} onChange={(event) => update({ ai_model: event.target.value })} placeholder="gpt-5-mini" /></label>
            {research.ai_provider !== "codex-cli" && <label className="field-label form-span"><span>Base URL</span><input className="mono" value={research.ai_base_url} onChange={(event) => update({ ai_base_url: event.target.value })} placeholder="https://api.openai.com/v1" spellCheck={false} /></label>}
            <label className="field-label"><span>超时（秒）</span><input type="number" min="10" max="300" value={research.ai_timeout_seconds} onChange={(event) => update({ ai_timeout_seconds: Number(event.target.value) })} /></label>
            <label className="field-label"><span>Temperature</span><input type="number" min="0" max="1" step="0.1" value={research.ai_temperature} onChange={(event) => update({ ai_temperature: Number(event.target.value) })} /></label>
            <label className="field-label"><span>Reasoning</span><select value={research.ai_reasoning_effort} onChange={(event) => update({ ai_reasoning_effort: event.target.value as DesktopSettings["research"]["ai_reasoning_effort"] })}><option value="low">low</option><option value="medium">medium</option><option value="high">high</option><option value="xhigh">xhigh</option></select></label>
          </div>
          <div className="button-row provider-actions">
            <button className="primary-button" disabled={busy !== null || !research.ai_model.trim() || (requiresKey && !configured)} onClick={() => void onTest()}>{busy === "ai-test" ? <LoaderCircle className="spin" size={15} /> : <Activity size={15} />}测试真实连接</button>
            <button className="secondary-button" disabled={busy !== null} onClick={() => void onSaveSettings()}><Save size={15} />保存配置</button>
          </div>
        </section>

        <section className="ruled-section form-section ai-credential-panel">
          <SectionHeading index="02" title={requiresKey ? "API Key 钥匙串" : "本地运行凭据"} note={requiresKey ? "Key 只保存在 macOS Keychain，不写入桌面配置和审计日志。" : "本地 Provider 不需要把 API Key 交给 BerkshireNexus。"} />
          {requiresKey ? (
            <form onSubmit={submitKey}>
              <div className="credential-state"><KeyRound size={18} /><div><strong>{configured ? "AI API Key 已配置" : "尚未保存 AI API Key"}</strong><span>{configured ? "前端无法读取或回显原文" : "OpenAI、OpenRouter、DeepSeek 等兼容服务均使用此安全槽位"}</span></div><StatusMark tone={configured ? "good" : "warn"}>{configured ? "可调用" : "待配置"}</StatusMark></div>
              <label className="field-label"><span>AI_PROVIDER_API_KEY</span><div className="secret-input"><KeyRound size={16} /><input type="password" value={key} onChange={(event) => setKey(event.target.value)} placeholder={configured ? "输入新 Key 可替换" : "粘贴 Provider API Key"} autoComplete="off" spellCheck={false} /></div></label>
              <div className="button-row"><button className="primary-button" type="submit" disabled={busy !== null || key.trim().length < 8}>{busy === "ai-key" ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}存入钥匙串</button>{configured && <button className="danger-text-button" type="button" disabled={busy !== null} onClick={() => void onDeleteKey()}><Trash2 size={15} />删除 Key</button>}</div>
            </form>
          ) : research.ai_provider === "ollama" ? (
            <div className="local-provider-note"><Database size={21} /><strong>连接本机 Ollama</strong><p>先安装并运行 Ollama，再拉取与 Model ID 相同的模型。请求只发往当前 Base URL。</p><code>ollama pull {research.ai_model || "qwen3:8b"}</code></div>
          ) : (
            <div className="local-provider-note"><BrainCircuit size={21} /><strong>启动独立的本地 Codex 任务</strong><p>这不是复用当前聊天内容。每次研究会通过本机 <code>codex exec --ephemeral --sandbox read-only</code> 创建一次独立请求，使用你在 Codex CLI 中的登录和模型用量。</p><span>选择此项即代表你明确允许研究周期消耗本地 Codex 用量。</span></div>
          )}
        </section>
      </div>

      <section className="ruled-section data-provider-section">
        <SectionHeading index="03" title="行情与新闻数据源" note="无需 AI Key 也能工作；每次研究都会记录 provider、数据时间、检索时间与失败原因。" />
        <div className="data-provider-grid">
          <div className="provider-card"><Database size={18} /><span>行情 / 历史</span><strong>Yahoo Finance Chart</strong><small>最新可用价、52 周区间、1 年日线与 Beta</small><StatusMark tone="good">默认启用</StatusMark></div>
          <div className="provider-card"><ClipboardList size={18} /><span>基本面</span><strong>Nasdaq Public API</strong><small>年报、EPS、公司资料与来源日期</small><StatusMark tone="good">默认启用</StatusMark></div>
          <div className="provider-card"><Search size={18} /><span>新闻 / 事件</span><strong>Yahoo + SEC + Google</strong><small>媒体标题、官方申报、时间、原文 URL 与证据 ID</small><label className="mini-switch"><input type="checkbox" checked={research.news_enabled} onChange={(event) => update({ news_enabled: event.target.checked })} /><span>{research.news_enabled ? "已启用" : "已关闭"}</span></label></div>
        </div>
        <div className="news-settings-row"><label className="field-label"><span>新闻回退策略</span><select value={research.news_provider} onChange={(event) => update({ news_provider: event.target.value as DesktopSettings["research"]["news_provider"] })}><option value="yahoo-google">Yahoo + SEC → Google RSS</option><option value="yahoo">仅 Yahoo Finance</option></select></label><label className="field-label"><span>每个标的最多</span><input type="number" min="1" max="12" value={research.max_news_items} onChange={(event) => update({ max_news_items: Number(event.target.value) })} /></label></div>
      </section>

      <section className="guardrail-statement"><ShieldCheck size={21} /><div><strong>AI 与真实资金之间没有直通路径</strong><p>AI 输出只作为带引用的研究附录；确定性综合分、仓位上限、换手、日损和 Live 权限均由独立代码控制。</p></div></section>
    </div>
  );
}

function Models({ snapshot, busy, onPromote }: { snapshot: AppSnapshot; busy: boolean; onPromote: () => Promise<void> }) {
  const { learning } = snapshot;
  const readiness = Math.min(100, learning.observation_count / learning.minimum_training_samples * 100);
  const champion = learning.champion;
  const challenger = learning.challenger;
  return (
    <div className="page-stack models-page">
      <section className="learning-ruler">
        <div>
          <span className="mono ruler-value">{learning.observation_count}</span>
          <span>已结算标签</span>
        </div>
        <div className="readiness-track">
          <span style={{ width: `${readiness}%` }} />
          <i style={{ left: "100%" }} />
        </div>
        <div className="ruler-target"><strong className="mono">{learning.minimum_training_samples}</strong><span>最低训练样本</span></div>
        <StatusMark tone={readiness >= 100 ? "good" : "warn"}>{readiness >= 100 ? "可训练" : `还差 ${learning.minimum_training_samples - learning.observation_count} 条`}</StatusMark>
      </section>

      <div className="model-registry">
        <section className="model-column champion-column">
          <SectionHeading index="01" title="Champion" note="当前用于产生可学习的预期收益，不拥有风控权限。" />
          {champion ? <ModelArtifactView artifact={champion} role="当前版本" /> : <EmptyState icon={FlaskConical} title="尚无 Champion" body="积累足够的延迟收益标签后，系统才会训练首个候选模型。" />}
        </section>
        <div className="registry-divider"><ArrowRight size={18} /><span>验证门</span></div>
        <section className="model-column challenger-column">
          <SectionHeading
            index="02"
            title="Challenger"
            note="只有时间切分验证优于 Champion，才允许人工或 Paper-only 自动晋升。"
            action={challenger && <button className="primary-button" disabled={busy} onClick={() => void onPromote()}>{busy ? <LoaderCircle className="spin" size={15} /> : <TrendingUp size={15} />}人工晋升</button>}
          />
          {challenger ? <ModelArtifactView artifact={challenger} role="待验证候选" /> : <EmptyState icon={Pause} title="当前没有候选模型" body="新标签会在后续周期触发训练；自动晋升默认关闭。" />}
        </section>
      </div>

      <section className="guardrail-statement">
        <ShieldCheck size={21} />
        <div><strong>学习边界不可跨越</strong><p>模型只拟合历史特征与未来收益；仓位、换手、日损、数据可信度与实盘权限全部由确定性代码控制。</p></div>
      </section>
    </div>
  );
}

function ModelArtifactView({ artifact, role }: { artifact: NonNullable<AppSnapshot["learning"]["champion"]>; role: string }) {
  const weights = Object.entries(artifact.model.weights).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  return (
    <div className="model-artifact">
      <span className="model-role">{role}</span>
      <strong className="mono model-version">{artifact.version}</strong>
      <dl className="model-metrics">
        <div><dt>方向准确率</dt><dd className="mono">{(artifact.validation_metrics.directional_accuracy * 100).toFixed(1)}%</dd></div>
        <div><dt>验证 RMSE</dt><dd className="mono">{artifact.validation_metrics.rmse.toFixed(4)}</dd></div>
        <div><dt>训练 / 验证</dt><dd className="mono">{artifact.training_sample_count} / {artifact.validation_metrics.sample_count}</dd></div>
        <div><dt>训练时间</dt><dd className="mono">{formatDate(artifact.trained_at_utc)}</dd></div>
      </dl>
      <div className="weight-list">
        <span>主要权重</span>
        {weights.slice(0, 5).map(([name, value]) => (
          <div key={name}><code>{name}</code><i className={value < 0 ? "negative" : ""} style={{ width: `${Math.min(Math.abs(value) * 500, 50)}%` }} /><strong className="mono">{value >= 0 ? "+" : ""}{value.toFixed(3)}</strong></div>
        ))}
      </div>
    </div>
  );
}

const riskFields: Array<{
  key: keyof Omit<RiskConfig, "allowed_symbols">;
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
  unit: string;
}> = [
  { key: "minimum_analysis_score", label: "最低研究分数", hint: "低于阈值不允许新增仓位", min: 60, max: 100, step: 1, unit: "分" },
  { key: "max_position_pct", label: "单标的仓位上限", hint: "默认安全上限为组合权益 10%", min: 1, max: 10, step: 0.5, unit: "%" },
  { key: "max_single_order_notional", label: "单笔名义金额上限", hint: "每一笔模拟订单的金额硬限制", min: 25, max: 10000, step: 25, unit: "USD" },
  { key: "max_daily_turnover_pct", label: "每日换手上限", hint: "累计买卖金额占期初权益比例", min: 1, max: 25, step: 1, unit: "%" },
  { key: "max_daily_loss_pct", label: "每日亏损熔断", hint: "触发后禁止增加风险，合法减仓仍允许", min: 0.1, max: 1, step: 0.1, unit: "%" },
];

function RiskPage({ settings, onSettings, onSave, busy }: { settings: DesktopSettings; onSettings: (next: DesktopSettings) => void; onSave: () => Promise<void>; busy: boolean }) {
  const updateRisk = (key: keyof RiskConfig, value: number | string[]) => onSettings({
    ...settings,
    risk: { ...settings.risk, [key]: value },
  });
  return (
    <div className="page-stack risk-page">
      <div className="risk-preamble">
        <ShieldCheck size={28} />
        <div><strong>模型之外的硬边界</strong><p>桌面界面只能把默认规则调得更严格。所有值在 Python 引擎中再次验证，修改前后都会留下配置状态。</p></div>
        <button className="primary-button" onClick={() => void onSave()} disabled={busy}>{busy ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}保存风控</button>
      </div>

      <section className="risk-controls ruled-section">
        <SectionHeading index="01" title="资本限制" note="拖动或直接输入。越靠左通常越保守，研究分数阈值相反。" />
        {riskFields.map((field) => {
          const value = settings.risk[field.key];
          const reversed = field.key === "minimum_analysis_score";
          return (
            <div className="risk-control" key={field.key}>
              <div><label htmlFor={`risk-${field.key}`}>{field.label}</label><p>{field.hint}</p></div>
              <input
                className={reversed ? "reversed-range" : ""}
                id={`risk-${field.key}`}
                type="range"
                min={field.min}
                max={field.max}
                step={field.step}
                value={value}
                onChange={(event) => updateRisk(field.key, Number(event.target.value))}
              />
              <div className="number-with-unit"><input aria-label={`${field.label}数值`} type="number" min={field.min} max={field.max} step={field.step} value={value} onChange={(event) => updateRisk(field.key, Number(event.target.value))} /><span>{field.unit}</span></div>
            </div>
          );
        })}
      </section>

      <div className="two-column equal">
        <section className="ruled-section form-section">
          <SectionHeading index="02" title="允许标的" note="留空代表使用 Agent 股票池；填写后成为额外的硬白名单。" />
          <label className="field-label">
            <span>股票代码白名单</span>
            <input placeholder="例如 AAPL MSFT（留空不额外限制）" value={settings.risk.allowed_symbols.join(" ")} onChange={(event) => updateRisk("allowed_symbols", Array.from(new Set(event.target.value.split(/[\s,，]+/).map((value) => value.toUpperCase().trim()).filter(Boolean))))} />
          </label>
        </section>
        <section className="locked-rules">
          <SectionHeading index="03" title="不可修改规则" />
          <ul>
            <li><LockKeyhole size={15} /><span><strong>实盘市价单</strong>始终禁用</span></li>
            <li><LockKeyhole size={15} /><span><strong>回退数据实盘买入</strong>始终禁止</span></li>
            <li><LockKeyhole size={15} /><span><strong>Binance tokenization</strong>固定为 false</span></li>
            <li><LockKeyhole size={15} /><span><strong>真实订单通道</strong>桌面 App 未开放</span></li>
          </ul>
        </section>
      </div>
    </div>
  );
}

function AuditPage({ snapshot }: { snapshot: AppSnapshot }) {
  const [selected, setSelected] = useState(0);
  const audit = snapshot.audits[selected];
  return (
    <div className="page-stack audit-page">
      <section className="audit-summary">
        <Metric label="已保留周期" value={snapshot.audits.length} detail="最近 30 份显示在桌面端" />
        <Metric label="模拟成交" value={snapshot.executions.length} detail="仅追加 JSONL 账本" />
        <Metric label="研究快照" value={snapshot.learning.snapshot_count} detail="等待延迟收益结算" />
      </section>
      {!snapshot.audits.length ? <EmptyState icon={ClipboardList} title="尚无审计记录" body="运行一次模拟周期后，这里会出现完整的证据与执行摘要。" /> : (
        <div className="audit-layout">
          <section className="audit-list">
            <SectionHeading index="01" title="周期记录" />
            {snapshot.audits.map((item, index) => (
              <button key={item.path} className={selected === index ? "active" : ""} onClick={() => setSelected(index)}>
                <span className="mono">{formatDate(item.generated_at_utc)}</span>
                <strong>{item.analysis_count} 研究 · {item.execution_count} 成交</strong>
                <ChevronRight size={15} />
              </button>
            ))}
          </section>
          {audit && (
            <section className="audit-detail ruled-section">
              <SectionHeading index="02" title="记录摘要" note="桌面端只展示安全摘要；原始 JSON 保存在本机状态目录。" />
              <span className="audit-stamp"><Check size={14} />本地审计文件</span>
              <dl className="definition-ledger">
                <div><dt>生成时间</dt><dd className="mono">{formatDate(audit.generated_at_utc)}</dd></div>
                <div><dt>研究数量</dt><dd className="mono">{audit.analysis_count}</dd></div>
                <div><dt>订单意图</dt><dd className="mono">{audit.order_count}</dd></div>
                <div><dt>模拟成交</dt><dd className="mono">{audit.execution_count}</dd></div>
                <div><dt>模型版本</dt><dd className="mono truncate">{audit.champion_version ?? "无 Champion"}</dd></div>
              </dl>
              <div className="audit-path"><span>文件路径</span><code>{audit.path}</code></div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function SettingsPage({
  settings,
  configured,
  busy,
  onSaveKey,
  onDeleteKey,
  onPreflight,
  onSaveSettings,
}: {
  settings: DesktopSettings;
  configured: boolean;
  busy: BusyAction;
  onSaveKey: (key: string) => Promise<void>;
  onDeleteKey: () => Promise<void>;
  onPreflight: () => Promise<void>;
  onSaveSettings: () => Promise<void>;
}) {
  const [key, setKey] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void onSaveKey(key).then(() => setKey("")).catch(() => undefined);
  };
  return (
    <div className="page-stack settings-page">
      <section className="connection-status">
        <div className={`connection-emblem ${configured ? "connected" : ""}`}>{configured ? <CircleCheck size={25} /> : <KeyRound size={25} />}</div>
        <div><span className="mono">BINANCE STOCKS / READ ONLY</span><h2>{configured ? "API Key 已存入 macOS 钥匙串" : "尚未配置 Binance API Key"}</h2><p>Key 只用于标的/行情预检；Secret 当前不需要，也不应提交给本项目。</p></div>
        <StatusMark tone={configured ? "good" : "warn"}>{configured ? "已配置" : "待配置"}</StatusMark>
      </section>

      <div className="two-column equal settings-grid">
        <section className="ruled-section form-section">
          <SectionHeading index="01" title="安全保存 API Key" note="输入内容不会写入 React 状态之外的文件，也不会返回给界面。" />
          <form onSubmit={submit}>
            <label className="field-label">
              <span>BINANCE_API_KEY</span>
              <div className="secret-input"><KeyRound size={16} /><input type="password" value={key} onChange={(event) => setKey(event.target.value)} placeholder={configured ? "输入新 Key 可替换现有值" : "粘贴只读 API Key"} autoComplete="off" spellCheck={false} /></div>
            </label>
            <div className="button-row">
              <button className="primary-button" type="submit" disabled={busy !== null || key.trim().length < 16}>{busy === "key" ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}存入钥匙串</button>
              {configured && <button className="danger-text-button" type="button" disabled={busy !== null} onClick={() => void onDeleteKey()}><Trash2 size={15} />删除 Key</button>}
            </div>
          </form>
          <div className="preflight-row">
            <div><strong>只读连通性检查</strong><p>检查 {settings.universe.join("、")} 的 Binance Stocks 可用性，不提交订单。</p></div>
            <button className="secondary-button" disabled={!configured || busy !== null} onClick={() => void onPreflight()}>{busy === "preflight" ? <LoaderCircle className="spin" size={15} /> : <Activity size={15} />}运行检查</button>
          </div>
        </section>

        <section className="ruled-section setup-guide">
          <SectionHeading index="02" title="如何获取 Binance API Key" />
          <ol>
            <li><span>1</span><div><strong>在 Binance 网页或 App 登录</strong><p>进入个人资料 → API 管理。创建新 API Key 时完成身份验证。</p></div></li>
            <li><span>2</span><div><strong>只开读取权限</strong><p>不要开启现货/合约交易和提现权限。若 Binance 支持 IP 白名单，建议配置。</p></div></li>
            <li><span>3</span><div><strong>复制 API Key</strong><p>粘贴到左侧并存入钥匙串。不要把 Key 发到聊天、GitHub、截图或 .env 提交中。</p></div></li>
          </ol>
          <a className="external-link" href="https://www.binance.com/en/my/settings/api-management" target="_blank" rel="noreferrer">打开 Binance API 管理 <ArrowUpRight size={14} /></a>
        </section>
      </div>

      <section className="ruled-section system-boundary">
        <SectionHeading index="03" title="当前系统边界" action={<button className="secondary-button" disabled={busy !== null} onClick={() => void onSaveSettings()}><Save size={15} />保存全部设置</button>} />
        <div className="boundary-grid">
          <div><CircleCheck size={17} /><span><strong>可以在 App 内完成</strong>保存/删除 Binance Key 与 Secret、AI Key、Provider 测试、当前数据/新闻研究、模拟交易、真实持仓读取、实盘预览与下单、撤单、订单恢复对账、Agent 启停、策略晋升、风控和审计。</span></div>
          <div><CircleAlert size={17} /><span><strong>仍需 Binance 官方界面</strong>开户、身份验证、Stocks 资格、API Key 创建、权限/IP 配置与账户合规确认。</span></div>
          <div><LockKeyhole size={17} /><span><strong>实盘双重确认</strong>真实下单需要 Secret 已配置、输入确认短语，并且每次提交都是显式操作；Agent 自动循环仍只走模拟盘。</span></div>
        </div>
      </section>
    </div>
  );
}

/** Real account, reconciliation, and the gated live execution path. */
function LivePage({
  settings,
  keyConfigured,
  secretConfigured,
  account,
  cycle,
  check,
  busy,
  onSaveSecret,
  onDeleteSecret,
  onVerify,
  onLoadAccount,
  onReconcile,
  onAcceptDisclaimer,
  onCancelAll,
  onRunCycle,
}: {
  settings: DesktopSettings;
  keyConfigured: boolean;
  secretConfigured: boolean;
  account: LiveAccount | null;
  cycle: LiveCycleResult | null;
  check: CredentialCheck | null;
  busy: BusyAction;
  onSaveSecret: (secret: string) => Promise<void>;
  onDeleteSecret: () => Promise<void>;
  onVerify: () => Promise<void>;
  onLoadAccount: () => Promise<void>;
  onReconcile: () => Promise<void>;
  onAcceptDisclaimer: () => Promise<void>;
  onCancelAll: () => Promise<void>;
  onRunCycle: (options: { confirmation: string; submit: boolean }) => Promise<void>;
}) {
  const [secret, setSecret] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const ready = keyConfigured && secretConfigured;
  const acknowledged = confirmation.trim() === LIVE_ACKNOWLEDGEMENT;

  const submitSecret = (event: FormEvent) => {
    event.preventDefault();
    void onSaveSecret(secret).then(() => setSecret("")).catch(() => undefined);
  };

  return (
    <div className="page-stack settings-page">
      <section className="connection-status">
        <div className={`connection-emblem ${ready ? "connected" : ""}`}>{ready ? <CircleCheck size={25} /> : <KeyRound size={25} />}</div>
        <div>
          <span className="mono">BINANCE STOCKS / LIVE</span>
          <h2>{ready ? "已具备读取真实账户与下单的凭证" : secretConfigured ? "缺少 API Key" : "缺少 API Secret"}</h2>
          <p>读取余额、持仓与挂单需要签名接口，因此必须同时配置 Key 和 Secret。下单额外需要输入确认短语。</p>
        </div>
        <StatusMark tone={ready ? "good" : "warn"}>{ready ? "凭证完整" : "待配置"}</StatusMark>
      </section>

      <div className="two-column equal settings-grid">
        <section className="ruled-section form-section">
          <SectionHeading index="01" title="保存 API Secret" note="Secret 仅存入 macOS 钥匙串，前端无法回显，也不会写入任何配置文件。" />
          <form onSubmit={submitSecret}>
            <label className="field-label">
              <span>BINANCE_API_SECRET</span>
              <div className="secret-input"><KeyRound size={16} /><input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder={secretConfigured ? "输入新 Secret 可替换现有值" : "粘贴 API Secret"} autoComplete="off" spellCheck={false} /></div>
            </label>
            <div className="button-row">
              <button className="primary-button" type="submit" disabled={busy !== null || secret.trim().length < 16}>{busy === "secret" ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}存入钥匙串</button>
              {secretConfigured && <button className="danger-text-button" type="button" disabled={busy !== null} onClick={() => void onDeleteSecret()}><Trash2 size={15} />删除 Secret</button>}
            </div>
          </form>
          <div className="preflight-row">
            <div><strong>凭证自检</strong><p>用一次未签名 + 一次签名调用定位问题：区分 Key 无效、Secret 不匹配、权限/IP 限制与本机时间偏差。</p></div>
            <button className="secondary-button" disabled={!ready || busy !== null} onClick={() => void onVerify()}>{busy === "verify" ? <LoaderCircle className="spin" size={15} /> : <ShieldCheck size={15} />}自检</button>
          </div>
          {check && (
            <div className={check.ok ? "" : "warn-note"}>
              {!check.ok && <p style={{ margin: 0 }}>{check.guidance}</p>}
              <table className="data-table">
                <tbody>
                  {check.checks.map((item) => (
                    <tr key={item.name}>
                      <td>{item.ok ? <StatusMark tone="good">通过</StatusMark> : <StatusMark tone="risk">失败</StatusMark>}</td>
                      <td className="mono">{item.name}</td>
                      <td className="muted">{item.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="preflight-row">
            <div><strong>签署美股免责声明</strong><p>Binance 要求先签署 US Equity Disclaimer，否则所有下单都会被拒绝（错误码 486410）。</p></div>
            <button className="secondary-button" disabled={!ready || busy !== null} onClick={() => void onAcceptDisclaimer()}>{busy === "disclaimer" ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}签署</button>
          </div>
        </section>

        <section className="ruled-section form-section">
          <SectionHeading index="02" title="真实账户" action={<button className="secondary-button" disabled={!ready || busy !== null} onClick={() => void onLoadAccount()}>{busy === "live-account" ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}读取</button>} />
          {!account ? (
            <p className="muted-note">尚未读取。点击「读取」从 Binance 拉取真实现金、持仓与挂单。</p>
          ) : (
            <>
              <div className="metric-row">
                <div><span>现金</span><strong>{money.format(account.cash)}</strong></div>
                <div><span>持仓市值</span><strong>{money.format(account.holdings_value)}</strong></div>
                <div><span>总权益</span><strong>{money.format(account.equity)}</strong></div>
              </div>
              {account.positions.length === 0 ? (
                <p className="muted-note">当前没有股票持仓。</p>
              ) : (
                <table className="data-table">
                  <thead><tr><th>标的</th><th>数量</th><th>价格</th><th>市值</th><th>占比</th><th>钱包</th></tr></thead>
                  <tbody>
                    {account.positions.map((position) => (
                      <tr key={position.ticker}>
                        <td className="mono">{position.ticker}</td>
                        <td>{position.quantity.toFixed(6)}</td>
                        <td>{position.price > 0 ? money.format(position.price) : "—"}</td>
                        <td>{position.market_value > 0 ? money.format(position.market_value) : "—"}</td>
                        <td>{position.weight_pct.toFixed(2)}%</td>
                        <td className="mono">{position.wallets.join("/")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {Object.keys(account.quote_errors).length > 0 && (
                <p className="muted-note">部分标的未取到价格，市值按 0 计：{Object.keys(account.quote_errors).join("、")}</p>
              )}
              {Object.keys(account.wallet_errors).length > 0 && (
                <p className="warn-note">钱包读取告警：{Object.entries(account.wallet_errors).map(([wallet, message]) => `${wallet}: ${message}`).join("；")}</p>
              )}
            </>
          )}
        </section>
      </div>

      <section className="ruled-section">
        <SectionHeading
          index="03"
          title="挂单与对账"
          note="重启后先对账：本地记录的每一笔订单都会去交易所核实真实状态。"
          action={
            <div className="button-row">
              <button className="secondary-button" disabled={!ready || busy !== null} onClick={() => void onReconcile()}>{busy === "reconcile" ? <LoaderCircle className="spin" size={15} /> : <Activity size={15} />}对账</button>
              <button className="danger-text-button" disabled={!ready || busy !== null} onClick={() => void onCancelAll()}><X size={15} />全部撤单</button>
            </div>
          }
        />
        {account?.pending_local_orders && <p className="warn-note">存在尚未确认状态的本地订单，请先对账再下单。</p>}
        {account && account.open_orders.length === 0 && !account.open_orders_error && <p className="muted-note">交易所无working挂单。</p>}
        {account?.open_orders_error && <p className="warn-note">挂单读取失败：{account.open_orders_error}</p>}
        {account && account.open_orders.length > 0 && (
          <table className="data-table">
            <thead><tr><th>标的</th><th>方向</th><th>类型</th><th>状态</th><th>数量</th><th>已成交</th><th>限价</th></tr></thead>
            <tbody>
              {account.open_orders.map((order) => (
                <tr key={order.order_id || order.client_order_id}>
                  <td className="mono">{order.ticker}</td>
                  <td>{order.side}</td>
                  <td>{order.order_type}</td>
                  <td>{order.status}</td>
                  <td>{order.quantity}</td>
                  <td>{order.filled_quantity}</td>
                  <td>{order.limit_price > 0 ? money.format(order.limit_price) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="ruled-section">
        <SectionHeading index="04" title="实盘执行" note={`标的：${settings.universe.join("、")}。预览不会下单；提交需要确认短语。`} />
        <div className="live-exec-grid">
          <label className="field-label">
            <span>确认短语（下单必填）</span>
            <div className="secret-input"><LockKeyhole size={16} /><input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder={LIVE_ACKNOWLEDGEMENT} autoComplete="off" spellCheck={false} /></div>
          </label>
          <div className="button-row">
            <button className="secondary-button" disabled={!ready || busy !== null} onClick={() => void onRunCycle({ confirmation: "", submit: false })}>{busy === "live-preview" ? <LoaderCircle className="spin" size={15} /> : <FlaskConical size={15} />}预览（不下单）</button>
            <button className="danger-button" disabled={!ready || busy !== null || !acknowledged} onClick={() => void onRunCycle({ confirmation: confirmation.trim(), submit: true })}>{busy === "live-submit" ? <LoaderCircle className="spin" size={15} /> : <Zap size={15} />}提交真实订单</button>
          </div>
        </div>
        {!acknowledged && confirmation.trim().length > 0 && <p className="warn-note">确认短语不匹配，必须与 {LIVE_ACKNOWLEDGEMENT} 完全一致。</p>}

        {cycle && (
          <div className="live-result">
            <div className="metric-row">
              <div><span>模式</span><strong>{cycle.mode === "live" ? "已提交实盘" : "仅预览"}</strong></div>
              <div><span>通过风控</span><strong>{cycle.approved_count} / {cycle.risk_decisions.length}</strong></div>
              <div><span>已提交</span><strong>{cycle.executions.length}</strong></div>
            </div>
            {cycle.blocked_reason && <p className="muted-note">未提交原因：{cycle.blocked_reason}</p>}
            {cycle.risk_decisions.length === 0 && <p className="muted-note">本轮没有产生任何目标订单。</p>}
            {cycle.risk_decisions.length > 0 && (
              <table className="data-table">
                <thead><tr><th>标的</th><th>方向</th><th>数量</th><th>限价</th><th>金额</th><th>风控</th></tr></thead>
                <tbody>
                  {cycle.risk_decisions.map((decision, index) => (
                    <tr key={`${decision.order.ticker}-${index}`}>
                      <td className="mono">{decision.order.ticker}</td>
                      <td>{decision.order.side}</td>
                      <td>{decision.order.quantity}</td>
                      <td>{decision.order.limit_price ? money.format(decision.order.limit_price) : "—"}</td>
                      <td>{money.format(decision.calculated_notional)}</td>
                      <td>{decision.approved ? <StatusMark tone="good">通过</StatusMark> : <span className="reject-reason">{decision.reasons.join("；")}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {cycle.executions.length > 0 && (
              <>
                <SectionHeading index="05" title="交易所回执" note="ACCEPTED 表示已挂单，不等于成交；成交状态由对账确认。" />
                <table className="data-table">
                  <thead><tr><th>标的</th><th>方向</th><th>状态</th><th>已成交</th><th>说明</th></tr></thead>
                  <tbody>
                    {cycle.executions.map((execution, index) => (
                      <tr key={`${execution.ticker}-${index}`}>
                        <td className="mono">{execution.ticker}</td>
                        <td>{execution.side}</td>
                        <td>{execution.status}</td>
                        <td>{execution.filled_quantity}</td>
                        <td className="muted">{execution.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<PageId>("overview");
  const [snapshot, setSnapshot] = useState<AppSnapshot | null>(null);
  const [settings, setSettings] = useState<DesktopSettings>(defaultSettings);
  const [reports, setReports] = useState<AnalysisReport[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [agentRunning, setAgentRunning] = useState(false);
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [aiKeyConfigured, setAIKeyConfigured] = useState(false);
  const [secretConfigured, setSecretConfigured] = useState(false);
  const [liveAccount, setLiveAccount] = useState<LiveAccount | null>(null);
  const [liveCycle, setLiveCycle] = useState<LiveCycleResult | null>(null);
  const [credentialCheck, setCredentialCheck] = useState<CredentialCheck | null>(null);
  const [busy, setBusy] = useState<BusyAction>("boot");
  const [toast, setToast] = useState<Toast | null>(null);
  const [modeExplanation, setModeExplanation] = useState(false);

  const notify = useCallback((tone: Toast["tone"], message: string) => {
    setToast({ id: Date.now(), tone, message });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setBusy("refresh");
    try {
      const [nextSnapshot, runtime] = await Promise.all([
        desktopBridge.snapshot(),
        desktopBridge.agentStatus(),
      ]);
      setSnapshot(nextSnapshot);
      setAgentRunning(runtime.running);
    } catch (error) {
      notify("error", `读取本地状态失败：${asError(error)}`);
    } finally {
      if (!quiet) setBusy(null);
    }
  }, [notify]);

  useEffect(() => {
    let alive = true;
    const boot = async () => {
      try {
        const [nextSettings, nextSnapshot, runtime, configured, aiConfigured, secretReady] = await Promise.all([
          desktopBridge.loadSettings(),
          desktopBridge.snapshot(),
          desktopBridge.agentStatus(),
          desktopBridge.keyStatus(),
          desktopBridge.aiKeyStatus(),
          desktopBridge.secretStatus(),
        ]);
        if (!alive) return;
        setSettings(nextSettings);
        setSnapshot(nextSnapshot);
        setAgentRunning(runtime.running);
        setKeyConfigured(configured);
        setAIKeyConfigured(aiConfigured);
        setSecretConfigured(secretReady);
      } catch (error) {
        if (alive) notify("error", `桌面应用初始化失败：${asError(error)}`);
      } finally {
        if (alive) setBusy(null);
      }
    };
    void boot();
    const timer = window.setInterval(() => void refresh(true), 15_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [notify, refresh]);

  const saveSettings = async (success = "设置已保存到本机") => {
    setBusy("save");
    try {
      await desktopBridge.saveSettings(settings);
      notify("success", success);
    } catch (error) {
      notify("error", `保存失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const analyze = async (tickers: string[]) => {
    setBusy("research");
    try {
      const values = await desktopBridge.analyzeWithSettings(tickers, settings);
      setReports(values);
      setSelectedTicker(values[0]?.ticker ?? null);
      notify("success", `已完成 ${values.length} 个标的的综合研究`);
    } catch (error) {
      notify("error", `研究失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const runCycle = async () => {
    setBusy("cycle");
    try {
      await desktopBridge.saveSettings(settings);
      const next = await desktopBridge.runCycle(settings);
      setSnapshot(next);
      notify("success", "Paper 周期完成，审计与模拟账本已更新");
    } catch (error) {
      notify("error", `周期执行失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const startAgent = async () => {
    setBusy("agent");
    try {
      await desktopBridge.saveSettings(settings);
      await desktopBridge.startAgent(settings);
      setAgentRunning(true);
      notify("success", "Paper Agent 已启动；关闭窗口后仍可在系统托盘运行");
      window.setTimeout(() => void refresh(true), 1200);
    } catch (error) {
      notify("error", `Agent 启动失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const stopAgent = async () => {
    setBusy("agent");
    try {
      await desktopBridge.stopAgent();
      setAgentRunning(false);
      await refresh(true);
      notify("info", "Paper Agent 已停止");
    } catch (error) {
      notify("error", `Agent 停止失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const promote = async () => {
    setBusy("promote");
    try {
      await desktopBridge.promoteModel();
      await refresh(true);
      notify("success", "Challenger 已人工晋升为 Champion");
    } catch (error) {
      notify("error", `模型晋升失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const saveKey = async (key: string) => {
    setBusy("key");
    try {
      await desktopBridge.saveKey(key);
      setKeyConfigured(true);
      notify("success", "API Key 已安全写入系统钥匙串");
    } catch (error) {
      notify("error", `保存 API Key 失败：${asError(error)}`);
      throw error;
    } finally {
      setBusy(null);
    }
  };

  const deleteKey = async () => {
    setBusy("key");
    try {
      await desktopBridge.deleteKey();
      setKeyConfigured(false);
      notify("info", "API Key 已从系统钥匙串删除");
    } catch (error) {
      notify("error", `删除 API Key 失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const preflight = async () => {
    setBusy("preflight");
    try {
      const result = await desktopBridge.preflight(settings.universe);
      const checked = Array.isArray(result.symbols) ? result.symbols.length : settings.universe.length;
      notify("success", `Binance 只读预检通过，已检查 ${checked} 个标的`);
    } catch (error) {
      notify("error", `Binance 预检失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const saveAIKey = async (key: string) => {
    setBusy("ai-key");
    try {
      await desktopBridge.saveAIKey(key);
      setAIKeyConfigured(true);
      notify("success", "AI Provider API Key 已安全写入系统钥匙串");
    } catch (error) {
      notify("error", `保存 AI API Key 失败：${asError(error)}`);
      throw error;
    } finally {
      setBusy(null);
    }
  };

  const deleteAIKey = async () => {
    setBusy("ai-key");
    try {
      await desktopBridge.deleteAIKey();
      setAIKeyConfigured(false);
      notify("info", "AI API Key 已从系统钥匙串删除");
    } catch (error) {
      notify("error", `删除 AI API Key 失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const testAI = async () => {
    setBusy("ai-test");
    try {
      await desktopBridge.saveSettings(settings);
      const result = await desktopBridge.testAIProvider(settings);
      if (result.status !== "ok") throw new Error(result.error ?? "Provider 未返回有效 JSON");
      notify("success", `${result.provider} / ${result.model} 连接成功，耗时 ${result.latency_ms} ms`);
    } catch (error) {
      notify("error", `AI Provider 连接失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const saveSecret = async (value: string) => {
    setBusy("secret");
    try {
      await desktopBridge.saveSecret(value);
      setSecretConfigured(true);
      notify("success", "Binance API Secret 已存入钥匙串");
    } catch (error) {
      notify("error", `保存 Secret 失败：${asError(error)}`);
      throw error;
    } finally {
      setBusy(null);
    }
  };

  const deleteSecret = async () => {
    setBusy("secret");
    try {
      await desktopBridge.deleteSecret();
      setSecretConfigured(false);
      setLiveAccount(null);
      notify("success", "Binance API Secret 已删除");
    } catch (error) {
      notify("error", `删除 Secret 失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const verifyCredentials = async () => {
    setBusy("verify");
    try {
      const value = await desktopBridge.verifyCredentials();
      setCredentialCheck(value);
      notify(value.ok ? "success" : "error", value.guidance);
    } catch (error) {
      notify("error", `凭证自检失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const loadLiveAccount = async () => {
    setBusy("live-account");
    try {
      const value = await desktopBridge.liveAccount();
      setLiveAccount(value);
      notify("success", `已读取真实账户：现金 ${money.format(value.cash)}，持仓 ${value.positions.length} 个`);
    } catch (error) {
      notify("error", `读取真实账户失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const reconcileLive = async () => {
    setBusy("reconcile");
    try {
      const value = await desktopBridge.liveReconcile();
      const settled = value.settled.length;
      const open = value.still_open.length;
      const unresolved = value.unresolved.length;
      notify(
        unresolved > 0 ? "error" : "success",
        `对账完成：核实 ${value.checked} 笔，已结清 ${settled}，仍挂单 ${open}，未解决 ${unresolved}`,
      );
      await loadLiveAccount();
    } catch (error) {
      notify("error", `对账失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const acceptDisclaimer = async () => {
    setBusy("disclaimer");
    try {
      await desktopBridge.liveAcceptDisclaimer();
      notify("success", "已签署 Binance 美股免责声明");
    } catch (error) {
      notify("error", `签署失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const cancelAllLive = async () => {
    setBusy("reconcile");
    try {
      await desktopBridge.liveCancelAll();
      notify("success", "已请求撤销全部挂单");
      await loadLiveAccount();
    } catch (error) {
      notify("error", `撤单失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const runLiveCycle = async (options: { confirmation: string; submit: boolean }) => {
    setBusy(options.submit ? "live-submit" : "live-preview");
    try {
      await desktopBridge.saveSettings(settings);
      const value = await desktopBridge.runLiveCycle(settings, options);
      setLiveCycle(value);
      if (value.submitted) {
        notify("success", `实盘已提交 ${value.executions.length} 笔订单，请对账确认成交`);
        await loadLiveAccount();
      } else {
        notify("info", `预览完成：${value.approved_count}/${value.risk_decisions.length} 笔通过风控，未提交任何订单`);
      }
    } catch (error) {
      notify("error", `实盘链路失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const meta = pageMeta[page];
  const pageContent = useMemo(() => {
    if (!snapshot) return <LoadingPage />;
    switch (page) {
      case "overview": return <Overview snapshot={snapshot} goTo={setPage} />;
      case "research": return <Research settings={settings} reports={reports} selectedTicker={selectedTicker} busy={busy === "research"} onAnalyze={analyze} onSelect={setSelectedTicker} />;
      case "ai": return <AISettingsPage settings={settings} configured={aiKeyConfigured} busy={busy} onSettings={setSettings} onSaveSettings={() => saveSettings("AI 与数据源配置已保存")} onSaveKey={saveAIKey} onDeleteKey={deleteAIKey} onTest={testAI} />;
      case "portfolio": return <Portfolio snapshot={snapshot} />;
      case "live": return <LivePage settings={settings} keyConfigured={keyConfigured} secretConfigured={secretConfigured} account={liveAccount} cycle={liveCycle} check={credentialCheck} busy={busy} onSaveSecret={saveSecret} onDeleteSecret={deleteSecret} onVerify={verifyCredentials} onLoadAccount={loadLiveAccount} onReconcile={reconcileLive} onAcceptDisclaimer={acceptDisclaimer} onCancelAll={cancelAllLive} onRunCycle={runLiveCycle} />;
      case "agent": return <AgentPage snapshot={snapshot} settings={settings} running={agentRunning} busy={busy === "agent" || busy === "cycle"} onSettings={setSettings} onStart={startAgent} onStop={stopAgent} onCycle={runCycle} />;
      case "models": return <Models snapshot={snapshot} busy={busy === "promote"} onPromote={promote} />;
      case "risk": return <RiskPage settings={settings} onSettings={setSettings} onSave={() => saveSettings("风控设置已保存")} busy={busy === "save"} />;
      case "audit": return <AuditPage snapshot={snapshot} />;
      case "settings": return <SettingsPage settings={settings} configured={keyConfigured} busy={busy} onSaveKey={saveKey} onDeleteKey={deleteKey} onPreflight={preflight} onSaveSettings={saveSettings} />;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, snapshot, settings, reports, selectedTicker, busy, agentRunning, keyConfigured, aiKeyConfigured, secretConfigured, liveAccount, liveCycle]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><span /><i /></div>
          <div><strong>BerkshireNexus</strong><span>ADAPTIVE RESEARCH AGENT</span></div>
        </div>
        <nav aria-label="主要导航">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)} key={item.id} aria-current={page === item.id ? "page" : undefined} title={item.description}>
                <Icon size={18} strokeWidth={1.8} />
                <span><strong>{item.label}</strong><small>{item.description}</small></span>
                {page === item.id && <i aria-hidden="true" />}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="agent-mini-status"><span className={agentRunning ? "active" : ""} /><div><strong>Paper Agent</strong><small>{agentRunning ? "后台运行中" : "已停止"}</small></div></div>
          <div className="build-label"><span>LOCAL-FIRST</span><span>v1.3.0</span></div>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div className="page-title">
            <span className="eyebrow mono">{meta.eyebrow}</span>
            <h1>{meta.title}</h1>
            <p>{meta.intro}</p>
          </div>
          <div className="topbar-actions">
            {snapshot?.demo && <span className="demo-badge">浏览器演示数据</span>}
            <div className="mode-selector" aria-label="交易模式">
              <button className={page === "live" ? "" : "active"} onClick={() => setPage("portfolio")}><FlaskConical size={14} />Paper</button>
              {/* Live is reachable once credentials exist; without a Secret it
                  explains what is missing instead of silently doing nothing. */}
              <button
                className={page === "live" ? "active" : secretConfigured && keyConfigured ? "" : "locked"}
                aria-describedby={secretConfigured && keyConfigured ? undefined : "live-mode-note"}
                onClick={() => (secretConfigured && keyConfigured ? setPage("live") : setModeExplanation(true))}
              >
                {secretConfigured && keyConfigured ? <Zap size={13} /> : <LockKeyhole size={13} />}Live
              </button>
            </div>
            <button className="icon-button" aria-label="刷新状态" title="刷新状态" disabled={busy !== null} onClick={() => void refresh()}><RefreshCw className={busy === "refresh" ? "spin" : ""} size={17} /></button>
          </div>
        </header>
        <div className="content-scroll">{pageContent}</div>
      </main>

      {toast && (
        <div className={`toast toast-${toast.tone}`} role="status" key={toast.id}>
          {toast.tone === "success" ? <CircleCheck size={18} /> : toast.tone === "error" ? <CircleAlert size={18} /> : <Activity size={18} />}
          <span>{toast.message}</span>
          <button aria-label="关闭提示" onClick={() => setToast(null)}><X size={15} /></button>
        </div>
      )}

      {modeExplanation && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setModeExplanation(false); }}>
          <section className="safety-modal" role="dialog" aria-modal="true" aria-labelledby="live-mode-title" id="live-mode-note">
            <button className="modal-close" aria-label="关闭" onClick={() => setModeExplanation(false)}><X size={17} /></button>
            <div className="modal-lock"><LockKeyhole size={25} /></div>
            <span className="mono">LIVE EXECUTION / CREDENTIALS REQUIRED</span>
            <h2 id="live-mode-title">实盘需要 Key 和 Secret 同时就位</h2>
            <p>读取真实现金、持仓与挂单，以及下单撤单，走的都是 Binance 签名接口，必须用 API Secret 做 HMAC-SHA256 签名。只有 API Key 是不够的。</p>
            <ul>
              <li>{keyConfigured ? <Check size={15} /> : <Pause size={15} />}API Key {keyConfigured ? "已配置" : "尚未配置"}</li>
              <li>{secretConfigured ? <Check size={15} /> : <Pause size={15} />}API Secret {secretConfigured ? "已配置" : "尚未配置（实盘页可保存）"}</li>
              <li><Check size={15} />订单恢复、成交对账与确定性风控已就绪</li>
            </ul>
            <button className="primary-button" onClick={() => { setModeExplanation(false); setPage("live"); }}>前往实盘页配置</button>
          </section>
        </div>
      )}
    </div>
  );
}
