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
  Newspaper,
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
  CredentialCheck,
  DailyBriefing,
  DesktopSettings,
  LiveAccount,
  LiveCycleResult,
  PageId,
  RiskConfig,
} from "./types";

type BusyAction =
  | "boot"
  | "briefing"
  | "save"
  | "key"
  | "ai-key"
  | "alpha-key"
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

/** Bare 2-dp number. Currency lives in the column header, not every cell. */
const plain = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

type SortKey = "unrealised_pnl" | "weight_pct" | "return_pct" | null;

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

const navItems: Array<{ id: PageId; label: string; description: string; icon: typeof Activity }> = [
  { id: "dashboard", label: "仪表盘", description: "收益与持仓", icon: LayoutDashboard },
  { id: "briefing", label: "日报", description: "AI 产业链埋伏", icon: Newspaper },
  { id: "strategy", label: "策略", description: "预览与下单", icon: Zap },
  { id: "settings", label: "设置", description: "凭证与风控", icon: SettingsIcon },
];

const pageMeta: Record<PageId, { eyebrow: string; title: string; intro: string }> = {
  dashboard: { eyebrow: "PORTFOLIO / LIVE", title: "仪表盘", intro: "真实持仓、成本价与收益。数据直接来自 Binance，不是本地推算。" },
  briefing: { eyebrow: "RESEARCH / DAILY", title: "AI 产业链埋伏日报", intro: "全市场筛选 → 分段扫描 → 结合成本价给出加仓/减仓判断。" },
  strategy: { eyebrow: "EXECUTION / GATED", title: "策略执行", intro: "自动出方案，真实下单需要你输入确认短语。" },
  settings: { eyebrow: "SYSTEM / CREDENTIALS", title: "设置", intro: "Key 与 Token 只写入 macOS 钥匙串，不进配置文件或日志。" },
};

/** Mirrors AI_PRESETS in src/research/config.py. */
const AI_PRESETS = {
  gateway: {
    label: "内部网关 (music-llm-gateway)",
    base_url: "https://music-llm-gateway.byted.org/v1",
    default_model: "gemini-3.7-flash-high",
  },
  gemini: {
    label: "Google Gemini (官方)",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
    default_model: "gemini-2.5-flash",
  },
} as const;

const ACTION_LABEL: Record<string, string> = {
  ADD: "建仓 / 加仓",
  HOLD: "持有",
  TRIM: "减仓",
  AVOID: "回避",
};

const ACTION_TONE: Record<string, "good" | "warn" | "risk" | "neutral"> = {
  ADD: "good",
  HOLD: "neutral",
  TRIM: "warn",
  AVOID: "risk",
};

const TASK_LABEL: Record<string, string> = {
  briefing: "生成日报",
  "live-account": "读取账户",
  "live-preview": "预览策略",
  "live-submit": "提交订单",
  reconcile: "对账",
  disclaimer: "签署声明",
  verify: "凭证自检",
  "ai-test": "测试模型",
  save: "保存设置",
  key: "保存 Key",
  secret: "保存 Secret",
  "ai-key": "保存 Token",
  "alpha-key": "保存 Key",
};

/** Actions that must not overlap: they mutate credentials, orders or state. */
const EXCLUSIVE: ReadonlySet<string> = new Set([
  "boot", "live-submit", "reconcile", "disclaimer",
  "key", "secret", "ai-key", "alpha-key",
]);

/**
 * Should a control be disabled given the running task?
 *
 * Previously every button keyed off `busy !== null`, so generating a briefing
 * (~80s) locked the entire app. Now a long read-only task only disables itself
 * and other exclusive actions.
 */
function blocked(busy: BusyAction, self?: BusyAction): boolean {
  if (busy === null) return false;
  if (self && busy === self) return true;
  return EXCLUSIVE.has(busy);
}

function pnlTone(value: number) {
  return value >= 0 ? "good" : "risk";
}

function signed(value: number, digits = 2) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

/** Dashboard: real holdings, cost basis and P&L straight from Binance. */
function Dashboard({
  account,
  busy,
  onRefresh,
  goTo,
}: {
  account: LiveAccount | null;
  busy: BusyAction;
  onRefresh: () => Promise<void>;
  goTo: (page: PageId) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>(null);
  const [sortDesc, setSortDesc] = useState(true);

  if (!account) {
    return (
      <div className="page-stack">
        <section className="ruled-section">
          <SectionHeading
            index="01"
            title="尚未读取真实账户"
            note="需要 API Key 与 Secret 都已配置（签名接口要求 Secret）。"
            action={
              <button className="primary-button" disabled={blocked(busy, "live-account")} onClick={() => void onRefresh()}>
                {busy === "live-account" ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}读取账户
              </button>
            }
          />
          <EmptyState
            title="没有账户数据"
            body="点击「读取账户」从 Binance 拉取持仓、成本价与收益；若报错请到设置页做凭证自检。"
          />
          <button className="text-button" onClick={() => goTo("settings")}>前往设置 <ChevronRight size={14} /></button>
        </section>
      </div>
    );
  }

  const unrealised = account.unrealised_pnl ?? 0;
  const unrealisedPct = account.unrealised_pnl_pct ?? 0;
  const incomplete = account.positions.filter((item) => item.cost_complete === false);

  const sorted = [...account.positions].sort((a, b) => {
    if (!sortKey) return a.ticker.localeCompare(b.ticker);
    const left = Number(a[sortKey] ?? 0);
    const right = Number(b[sortKey] ?? 0);
    return sortDesc ? right - left : left - right;
  });

  const toggleSort = (key: Exclude<SortKey, null>) => {
    if (sortKey === key) {
      // third click clears back to alphabetical
      if (sortDesc) setSortDesc(false);
      else { setSortKey(null); setSortDesc(true); }
    } else {
      setSortKey(key);
      setSortDesc(true);
    }
  };

  const arrow = (key: Exclude<SortKey, null>) =>
    sortKey === key ? (sortDesc ? " ↓" : " ↑") : "";

  return (
    <div className="page-stack">
      <section className="overview-strip" aria-label="账户概览">
        <Metric label="股票市值" value={money.format(account.holdings_value)} detail={`${account.positions.length} 个持仓`} />
        <Metric
          label="浮动盈亏"
          value={`${unrealised >= 0 ? "+" : ""}${money.format(unrealised)}`}
          detail={`${signed(unrealisedPct)}% · 成本 ${money.format(account.total_cost ?? 0)}`}
          tone={pnlTone(unrealised)}
        />
        <Metric label="理财 Earn" value={money.format(account.earn_total_usdt ?? 0)} detail="不参与风控分母" />
        <Metric label="净资产" value={money.format(account.net_worth ?? account.equity)} detail={`可交易 ${money.format(account.equity)}`} />
      </section>

      <section className="ruled-section">
        <SectionHeading
          index="01"
          title="持仓明细"
          note="金额单位 USD。成本价由成交记录推导（Binance 无成本价接口）。点击表头可排序。"
          action={
            <button className="secondary-button" disabled={blocked(busy, "live-account")} onClick={() => void onRefresh()}>
              {busy === "live-account" ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}刷新
            </button>
          }
        />
        {account.positions.length === 0 ? (
          <EmptyState title="当前没有股票持仓" body="日报页会给出建仓候选，策略页负责下单。" />
        ) : (
          <table className="data-table numeric-table">
            <thead>
              <tr>
                <th>标的</th>
                <th>数量</th>
                <th>成本价 (USD)</th>
                <th>现价 (USD)</th>
                <th>市值 (USD)</th>
                <th>
                  <button className="sort-header" onClick={() => toggleSort("unrealised_pnl")}>
                    浮动盈亏 (USD){arrow("unrealised_pnl")}
                  </button>
                </th>
                <th>
                  <button className="sort-header" onClick={() => toggleSort("return_pct")}>
                    收益率 %{arrow("return_pct")}
                  </button>
                </th>
                <th>
                  <button className="sort-header" onClick={() => toggleSort("weight_pct")}>
                    占比 %{arrow("weight_pct")}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((position) => {
                const pnl = position.unrealised_pnl ?? 0;
                const known = (position.average_cost ?? 0) > 0;
                return (
                  <tr key={position.ticker}>
                    <td className="mono">
                      {position.ticker}
                      {position.tokenized ? <span className="muted"> ·b</span> : null}
                      {position.cost_complete === false ? <span className="muted" title="部分成交早于查询窗口，成本不完整"> *</span> : null}
                    </td>
                    <td>{position.quantity.toFixed(4)}</td>
                    <td>{known ? plain.format(position.average_cost ?? 0) : "—"}</td>
                    <td>{position.price ? plain.format(position.price) : "—"}</td>
                    <td>{plain.format(position.market_value)}</td>
                    <td className={pnl >= 0 ? "pnl-up" : "pnl-down"}>
                      {known ? `${pnl >= 0 ? "+" : ""}${plain.format(pnl)}` : "—"}
                    </td>
                    <td className={pnl >= 0 ? "pnl-up" : "pnl-down"}>
                      {known ? signed(position.return_pct ?? 0) : "—"}
                    </td>
                    <td>{position.weight_pct.toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {incomplete.length > 0 && (
          <p className="muted-note">
            * {incomplete.map((item) => item.ticker).join("、")} 有成交早于查询窗口，浮动盈亏只按已知成本的那部分股数计算。
          </p>
        )}
      </section>

      {(account.open_orders.length > 0 || account.pending_local_orders) && (
        <section className="ruled-section">
          <SectionHeading index="02" title="未完成订单" note="重启后应先对账，再决定是否下新单。" />
          {account.pending_local_orders && <p className="warn-note">有本地记录未确认状态的订单，请到策略页对账。</p>}
          {account.open_orders.length > 0 && (
            <table className="data-table">
              <thead><tr><th>标的</th><th>方向</th><th>状态</th><th>数量</th><th>已成交</th><th>限价</th></tr></thead>
              <tbody>
                {account.open_orders.map((order) => (
                  <tr key={order.order_id || order.client_order_id}>
                    <td className="mono">{order.ticker}</td>
                    <td>{order.side}</td>
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
      )}
    </div>
  );
}

/** Daily briefing: screening, segment scan, and cost-aware ADD/TRIM calls. */
function BriefingPage({
  briefing,
  aiConfigured,
  busy,
  elapsed,
  onGenerate,
  goTo,
}: {
  briefing: DailyBriefing | null;
  aiConfigured: boolean;
  busy: BusyAction;
  elapsed: number;
  onGenerate: () => Promise<void>;
  goTo: (page: PageId) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="page-stack">
      <section className="ruled-section">
        <SectionHeading
          index="01"
          title="生成今日日报"
          note="全市场筛选 → 取交易场所实时价 → 确定性评分 → 结合成本价判断加减仓。"
          action={
            <button className="primary-button" disabled={blocked(busy, "briefing")} onClick={() => void onGenerate()}>
              {busy === "briefing" ? <LoaderCircle className="spin" size={15} /> : <Newspaper size={15} />}
              {busy === "briefing" ? `生成中… ${elapsed}s（约 80s）` : "生成日报"}
            </button>
          }
        />
        {!briefing && (
          <EmptyState
            title="还没有日报"
            body={aiConfigured
              ? "点击「生成日报」跑一轮完整扫描。"
              : "点击「生成日报」可跑确定性扫描；配置 AI 模型后还会给出带引用的埋伏理由。"}
          />
        )}
        {!aiConfigured && (
          <p className="muted-note">
            AI 未配置，日报只包含确定性评分。<button className="text-button" onClick={() => goTo("settings")}>去配置模型 <ChevronRight size={13} /></button>
          </p>
        )}
      </section>

      {briefing && (
        <>
          <section className="ruled-section">
            <SectionHeading
              index="02"
              title="今日判断"
              note={`扫描 ${briefing.screened.total_listings} 只美股，可交易 ${briefing.screened.tradable_listings} 只，入选 ${briefing.screened.shortlist_size} 只`}
            />
            {briefing.ai_status === "ok" && briefing.market_note ? (
              <p className="market-note">{briefing.market_note}</p>
            ) : (
              <p className="muted-note">
                {briefing.ai_status === "error"
                  ? `AI 综合失败：${briefing.ai_error}`
                  : "AI 综合未启用，以下结论来自确定性引擎。"}
              </p>
            )}
            <div className="metric-row">
              <div><span>股票市值</span><strong>{money.format(briefing.portfolio.holdings_value)}</strong></div>
              <div><span>浮动盈亏</span><strong className={pnlTone(briefing.portfolio.unrealised_pnl) === "good" ? "pnl-up" : "pnl-down"}>{signed(briefing.portfolio.unrealised_pnl_pct)}%</strong></div>
              <div><span>持仓数</span><strong>{briefing.portfolio.position_count}</strong></div>
              <div><span>净资产</span><strong>{money.format(briefing.portfolio.net_worth)}</strong></div>
            </div>
          </section>

          <section className="ruled-section">
            <SectionHeading index="03" title="分段扫描" note="上游瓶颈到下游变现，逐段看强弱。" />
            <table className="data-table">
              <thead><tr><th>产业链分段</th><th>候选</th><th>均分</th><th>均涨跌</th><th>段内最佳</th></tr></thead>
              <tbody>
                {briefing.segments.map((segment) => (
                  <tr key={segment.segment}>
                    <td><strong>{segment.label}</strong><br /><span className="muted">{segment.role}</span></td>
                    <td>{segment.candidate_count}</td>
                    <td>{segment.average_score.toFixed(1)}</td>
                    <td className={segment.average_change_pct >= 0 ? "pnl-up" : "pnl-down"}>{signed(segment.average_change_pct)}%</td>
                    <td className="mono">{segment.best_ticker} <span className="muted">({segment.best_score})</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="ruled-section">
            <SectionHeading index="04" title="今日建议" note="判定由确定性规则给出；AI 负责解释与反驳，不负责决定。" />
            <div className="idea-list">
              {briefing.ideas.map((idea) => (
                <div className={`idea-card action-${idea.action.toLowerCase()}`} key={idea.ticker}>
                  <button className="idea-head" onClick={() => setExpanded(expanded === idea.ticker ? null : idea.ticker)}>
                    <div className="idea-title">
                      <strong className="mono">{idea.ticker}</strong>
                      <StatusMark tone={ACTION_TONE[idea.action] ?? "neutral"}>{ACTION_LABEL[idea.action] ?? idea.action}</StatusMark>
                      <span className="muted">{idea.segment_label}</span>
                    </div>
                    <div className="idea-stats">
                      <span>分 <strong>{idea.score.toFixed(1)}</strong></span>
                      <span>动量 <strong>{idea.momentum_score.toFixed(1)}</strong></span>
                      <span>{money.format(idea.price)} <em className={idea.change_pct >= 0 ? "pnl-up" : "pnl-down"}>{signed(idea.change_pct)}%</em></span>
                      {idea.buzz_crowded && <span className="crowded-tag" title={idea.buzz_note}>拥挤</span>}
                      {idea.held_quantity > 0 ? (
                        <span>成本 {money.format(idea.average_cost)} <em className={idea.unrealised_pct >= 0 ? "pnl-up" : "pnl-down"}>{signed(idea.unrealised_pct, 1)}%</em></span>
                      ) : <span className="muted">未持仓</span>}
                      <ChevronRight size={14} className={expanded === idea.ticker ? "rotated" : ""} />
                    </div>
                  </button>
                  {expanded === idea.ticker && (
                    <div className="idea-body">
                      <p><strong>判定依据</strong></p>
                      <ul>{idea.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
                      <p className="muted">
                        仓位上限 {idea.position_cap_pct.toFixed(1)}%
                        {idea.held_quantity > 0 ? ` · 当前 ${idea.weight_pct.toFixed(2)}%` : ""}
                        {" · "}安全边际 {signed(idea.margin_of_safety_pct, 1)}%
                        {" · "}瓶颈 L{idea.chokepoint_level}
                      </p>
                      {idea.ai_summary && (
                        <>
                          <p><strong>AI 综合（信心 {idea.ai_action_bias || "—"}）</strong></p>
                          {idea.ai_summary.split("\n").map((line, index) => <p key={index}>{line}</p>)}
                          {idea.ai_citations.length > 0 && (
                            <p className="muted">引用证据：{idea.ai_citations.join("、")}</p>
                          )}
                        </>
                      )}
                      {(idea.buzz_note || idea.news_available) && (
                        <>
                          <p><strong>关注度与情绪</strong></p>
                          <ul>
                            {idea.buzz_note && <li>{idea.buzz_note}</li>}
                            {idea.news_available && (
                              <li>
                                新闻情绪 {idea.news_label}（{idea.news_score >= 0 ? "+" : ""}{idea.news_score.toFixed(3)}），
                                共 {idea.news_article_count} 篇
                              </li>
                            )}
                          </ul>
                          <p className="muted">社交热度仅作拥挤度参考，不构成买入理由。</p>
                        </>
                      )}
                      {idea.news.length > 0 && (
                        <>
                          <p><strong>新闻证据</strong></p>
                          <ul>
                            {idea.news.map((item) => (
                              <li key={item.evidence_id}>
                                <span className="mono muted">{item.evidence_id}</span>{" "}
                                <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
                                <span className="muted"> — {item.publisher}</span>
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="button-row">
              <button className="primary-button" onClick={() => goTo("strategy")}>去策略页执行 <ArrowRight size={15} /></button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
/** Strategy: preview a cycle, then submit real orders behind two gates. */
function StrategyPage({
  settings,
  cycle,
  account,
  ready,
  busy,
  elapsed,
  onSettings,
  onSaveSettings,
  onPreview,
  onSubmit,
  onReconcile,
  onCancelAll,
  goTo,
}: {
  settings: DesktopSettings;
  cycle: LiveCycleResult | null;
  account: LiveAccount | null;
  ready: boolean;
  busy: BusyAction;
  elapsed: number;
  onSettings: (next: DesktopSettings) => void;
  onSaveSettings: () => Promise<void>;
  onPreview: () => Promise<void>;
  onSubmit: (confirmation: string) => Promise<void>;
  onReconcile: () => Promise<void>;
  onCancelAll: () => Promise<void>;
  goTo: (page: PageId) => void;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [universeText, setUniverseText] = useState(settings.universe.join(", "));
  const acknowledged = confirmation.trim() === LIVE_ACKNOWLEDGEMENT;
  const approved = cycle?.risk_decisions.filter((item) => item.approved) ?? [];

  const commitUniverse = () => {
    const next = universeText
      .split(/[,，\s]+/)
      .map((value) => value.trim().toUpperCase())
      .filter(Boolean);
    if (next.length) onSettings({ ...settings, universe: next });
  };

  if (!ready) {
    return (
      <div className="page-stack">
        <section className="ruled-section">
          <SectionHeading index="01" title="缺少凭证" note="真实下单需要 API Key 与 Secret 都已配置。" />
          <EmptyState title="无法执行策略" body="请先到设置页保存 Binance Key 与 Secret，并完成凭证自检。" />
          <button className="primary-button" onClick={() => goTo("settings")}>前往设置 <ChevronRight size={14} /></button>
        </section>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <section className="ruled-section">
        <SectionHeading
          index="01"
          title="标的池"
          note="留空则用日报入选名单。逗号或空格分隔。"
          action={
            <button className="secondary-button" disabled={busy !== null} onClick={() => { commitUniverse(); void onSaveSettings(); }}>
              <Save size={15} />保存
            </button>
          }
        />
        <label className="field-label">
          <span>UNIVERSE</span>
          <input
            value={universeText}
            onChange={(event) => setUniverseText(event.target.value)}
            onBlur={commitUniverse}
            placeholder="AAPL, NVDA, TSM"
            spellCheck={false}
          />
        </label>
        <p className="muted-note">单笔上限 {money.format(settings.risk.max_single_order_notional)} · 单一标的上限 {settings.risk.max_position_pct}% · 可在设置页调整</p>
      </section>

      <section className="ruled-section">
        <SectionHeading
          index="02"
          title="执行"
          note="预览不下单。提交需要逐字输入确认短语，且每次提交都是显式操作。"
          action={
            <div className="button-row">
              <button className="secondary-button" disabled={blocked(busy, "reconcile")} onClick={() => void onReconcile()}>
                {busy === "reconcile" ? <LoaderCircle className="spin" size={15} /> : <Activity size={15} />}对账
              </button>
              <button className="danger-text-button" disabled={blocked(busy, "reconcile")} onClick={() => void onCancelAll()}>
                <X size={15} />全部撤单
              </button>
            </div>
          }
        />
        <div className="live-exec-grid">
          <label className="field-label">
            <span>确认短语（下单必填）</span>
            <div className="secret-input">
              <LockKeyhole size={16} />
              <input
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder={LIVE_ACKNOWLEDGEMENT}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
          </label>
          <div className="button-row">
            <button className="secondary-button" disabled={blocked(busy, "live-preview")} onClick={() => void onPreview()}>
              {busy === "live-preview" ? <LoaderCircle className="spin" size={15} /> : <FlaskConical size={15} />}
              {busy === "live-preview" ? `预览中… ${elapsed}s` : "预览（不下单）"}
            </button>
            <button
              className="danger-button"
              disabled={blocked(busy, "live-submit") || !acknowledged || approved.length === 0}
              onClick={() => void onSubmit(confirmation.trim())}
            >
              {busy === "live-submit" ? <LoaderCircle className="spin" size={15} /> : <Zap size={15} />}
              提交 {approved.length > 0 ? `${approved.length} 笔` : ""}真实订单
            </button>
          </div>
        </div>
        {confirmation.trim().length > 0 && !acknowledged && (
          <p className="warn-note">确认短语不匹配，必须与 {LIVE_ACKNOWLEDGEMENT} 完全一致。</p>
        )}
        {account?.pending_local_orders && <p className="warn-note">存在状态未确认的订单，请先对账再下新单。</p>}
      </section>

      {cycle && (
        <section className="ruled-section">
          <SectionHeading
            index="03"
            title={cycle.submitted ? "已提交" : "预览结果"}
            note={cycle.blocked_reason ? `未提交原因：${cycle.blocked_reason}` : undefined}
          />
          <div className="metric-row">
            <div><span>模式</span><strong>{cycle.submitted ? "已提交实盘" : "仅预览"}</strong></div>
            <div><span>组合权益（风控分母）</span><strong>{money.format(cycle.equity ?? 0)}</strong></div>
            <div><span>通过风控</span><strong>{cycle.approved_count} / {cycle.risk_decisions.length}</strong></div>
          </div>
          {cycle.unpriced_positions && cycle.unpriced_positions.length > 0 && (
            <p className="warn-note">以下持仓取不到报价，权益被低估，实盘提交已被拒绝：{cycle.unpriced_positions.join("、")}</p>
          )}
          {cycle.risk_decisions.length === 0 ? (
            <p className="muted-note">本轮没有产生任何目标订单（已在目标仓位附近）。</p>
          ) : (
            <table className="data-table">
              <thead><tr><th>标的</th><th>方向</th><th>数量</th><th>限价</th><th>金额</th><th>风控</th></tr></thead>
              <tbody>
                {cycle.risk_decisions.map((decision, index) => (
                  <tr key={`${decision.order.ticker}-${index}`}>
                    <td className="mono">{decision.order.ticker}</td>
                    <td className={decision.order.side === "BUY" ? "pnl-up" : "pnl-down"}>{decision.order.side}</td>
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
              <SectionHeading index="04" title="交易所回执" note="ACCEPTED 表示已挂单，不等于成交；成交由对账确认。" />
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
        </section>
      )}
    </div>
  );
}

/** Settings: credentials, AI model, and the risk limits. */
function SettingsPage({
  settings,
  keyConfigured,
  secretConfigured,
  aiConfigured,
  alphaConfigured,
  check,
  busy,
  onSettings,
  onSaveSettings,
  onSaveKey,
  onDeleteKey,
  onSaveSecret,
  onDeleteSecret,
  onSaveAIKey,
  onDeleteAIKey,
  onSaveAlphaKey,
  onDeleteAlphaKey,
  onVerify,
  onTestAI,
  onAcceptDisclaimer,
}: {
  settings: DesktopSettings;
  keyConfigured: boolean;
  secretConfigured: boolean;
  aiConfigured: boolean;
  alphaConfigured: boolean;
  check: CredentialCheck | null;
  busy: BusyAction;
  onSettings: (next: DesktopSettings) => void;
  onSaveSettings: () => Promise<void>;
  onSaveKey: (value: string) => Promise<void>;
  onDeleteKey: () => Promise<void>;
  onSaveSecret: (value: string) => Promise<void>;
  onDeleteSecret: () => Promise<void>;
  onSaveAIKey: (value: string) => Promise<void>;
  onDeleteAIKey: () => Promise<void>;
  onSaveAlphaKey: (value: string) => Promise<void>;
  onDeleteAlphaKey: () => Promise<void>;
  onVerify: () => Promise<void>;
  onTestAI: () => Promise<void>;
  onAcceptDisclaimer: () => Promise<void>;
}) {
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const [aiKey, setAIKey] = useState("");
  const [avKey, setAVKey] = useState("");
  const research = settings.research;
  const preset = research.ai_provider === "gemini" ? AI_PRESETS.gemini : AI_PRESETS.gateway;

  const applyPreset = (id: keyof typeof AI_PRESETS) => {
    const spec = AI_PRESETS[id];
    onSettings({
      ...settings,
      research: {
        ...research,
        ai_enabled: true,
        ai_provider: id === "gemini" ? "gemini" : "openai-compatible",
        ai_base_url: spec.base_url,
        ai_model: spec.default_model,
      },
    });
  };

  return (
    <div className="page-stack settings-page">
      <section className="connection-status">
        <div className={`connection-emblem ${keyConfigured && secretConfigured ? "connected" : ""}`}>
          {keyConfigured && secretConfigured ? <CircleCheck size={25} /> : <KeyRound size={25} />}
        </div>
        <div>
          <span className="mono">BINANCE STOCKS</span>
          <h2>{keyConfigured && secretConfigured ? "凭证完整" : secretConfigured ? "缺少 API Key" : "缺少 API Secret"}</h2>
          <p>读取余额、持仓与下单都走签名接口，必须同时配置 Key 和 Secret。Secret 只在创建密钥时显示一次。</p>
        </div>
        <StatusMark tone={keyConfigured && secretConfigured ? "good" : "warn"}>
          {keyConfigured && secretConfigured ? "可用" : "待配置"}
        </StatusMark>
      </section>

      <div className="two-column equal settings-grid">
        <section className="ruled-section form-section">
          <SectionHeading index="01" title="Binance 凭证" note="只写入 macOS 钥匙串；前端无法回显。" />
          <label className="field-label">
            <span>BINANCE_API_KEY</span>
            <div className="secret-input">
              <KeyRound size={16} />
              <input type="password" value={key} onChange={(event) => setKey(event.target.value)} placeholder={keyConfigured ? "输入新 Key 可替换" : "粘贴 API Key"} autoComplete="off" spellCheck={false} />
            </div>
          </label>
          <div className="button-row">
            <button className="primary-button" disabled={busy !== null || key.trim().length < 16} onClick={() => void onSaveKey(key).then(() => setKey("")).catch(() => undefined)}>
              {busy === "key" ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}存 Key
            </button>
            {keyConfigured && <button className="danger-text-button" disabled={busy !== null} onClick={() => void onDeleteKey()}><Trash2 size={15} />删除</button>}
          </div>

          <label className="field-label">
            <span>BINANCE_API_SECRET</span>
            <div className="secret-input">
              <KeyRound size={16} />
              <input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder={secretConfigured ? "输入新 Secret 可替换" : "粘贴 API Secret"} autoComplete="off" spellCheck={false} />
            </div>
          </label>
          <div className="button-row">
            <button className="primary-button" disabled={busy !== null || secret.trim().length < 16} onClick={() => void onSaveSecret(secret).then(() => setSecret("")).catch(() => undefined)}>
              {busy === "secret" ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}存 Secret
            </button>
            {secretConfigured && <button className="danger-text-button" disabled={busy !== null} onClick={() => void onDeleteSecret()}><Trash2 size={15} />删除</button>}
          </div>

          <div className="preflight-row">
            <div><strong>凭证自检</strong><p>一次未签名 + 一次签名调用，区分 Key 无效 / Secret 不匹配 / 权限或 IP 限制 / 时间偏差。</p></div>
            <button className="secondary-button" disabled={busy !== null || !keyConfigured || !secretConfigured} onClick={() => void onVerify()}>
              {busy === "verify" ? <LoaderCircle className="spin" size={15} /> : <ShieldCheck size={15} />}自检
            </button>
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
            <div><strong>签署美股免责声明</strong><p>Binance 要求先签署，否则所有订单被拒（486410）。</p></div>
            <button className="secondary-button" disabled={busy !== null || !keyConfigured || !secretConfigured} onClick={() => void onAcceptDisclaimer()}>
              {busy === "disclaimer" ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}签署
            </button>
          </div>
        </section>

        <section className="ruled-section form-section">
          <SectionHeading index="02" title="AI 模型" note="用于日报的埋伏理由综合；判定本身不依赖模型。" />
          <div className="button-row">
            <button className="secondary-button" onClick={() => applyPreset("gateway")}>用内部网关</button>
            <button className="secondary-button" onClick={() => applyPreset("gemini")}>用 Gemini 官方</button>
          </div>
          <label className="field-label">
            <span>BASE URL</span>
            <input value={research.ai_base_url} onChange={(event) => onSettings({ ...settings, research: { ...research, ai_base_url: event.target.value } })} spellCheck={false} />
          </label>
          <label className="field-label">
            <span>模型</span>
            <input value={research.ai_model} onChange={(event) => onSettings({ ...settings, research: { ...research, ai_model: event.target.value } })} spellCheck={false} placeholder={preset.default_model} />
          </label>
          <label className="field-label">
            <span>API TOKEN</span>
            <div className="secret-input">
              <KeyRound size={16} />
              <input type="password" value={aiKey} onChange={(event) => setAIKey(event.target.value)} placeholder={aiConfigured ? "输入新 Token 可替换" : "粘贴 Token"} autoComplete="off" spellCheck={false} />
            </div>
          </label>
          <div className="button-row">
            <button className="primary-button" disabled={busy !== null || aiKey.trim().length < 8} onClick={() => void onSaveAIKey(aiKey).then(() => setAIKey("")).catch(() => undefined)}>
              {busy === "ai-key" ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}存 Token
            </button>
            {aiConfigured && <button className="danger-text-button" disabled={busy !== null} onClick={() => void onDeleteAIKey()}><Trash2 size={15} />删除</button>}
            <button className="secondary-button" disabled={busy !== null || !research.ai_model.trim()} onClick={() => void onTestAI()}>
              {busy === "ai-test" ? <LoaderCircle className="spin" size={15} /> : <Activity size={15} />}测试连接
            </button>
          </div>
          <label className="checkbox-row">
            <input type="checkbox" checked={research.ai_enabled} onChange={(event) => onSettings({ ...settings, research: { ...research, ai_enabled: event.target.checked } })} />
            <span>启用 AI 综合</span>
          </label>

          <SectionHeading index="03" title="情绪数据源" note="Reddit 关注度免费无需 Key；新闻情绪需要 Alpha Vantage 免费 Key（25 次/天）。" />
          <label className="field-label">
            <span>ALPHAVANTAGE_API_KEY（可选）</span>
            <div className="secret-input">
              <KeyRound size={16} />
              <input type="password" value={avKey} onChange={(event) => setAVKey(event.target.value)} placeholder={alphaConfigured ? "输入新 Key 可替换" : "粘贴免费 Key"} autoComplete="off" spellCheck={false} />
            </div>
          </label>
          <div className="button-row">
            <button className="primary-button" disabled={busy !== null || avKey.trim().length < 8} onClick={() => void onSaveAlphaKey(avKey).then(() => setAVKey("")).catch(() => undefined)}>
              {busy === "alpha-key" ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}存 Key
            </button>
            {alphaConfigured && <button className="danger-text-button" disabled={busy !== null} onClick={() => void onDeleteAlphaKey()}><Trash2 size={15} />删除</button>}
            <a className="external-link" href="https://www.alphavantage.co/support/#api-key" target="_blank" rel="noreferrer">领取免费 Key <ArrowUpRight size={13} /></a>
          </div>
          <p className="muted-note">未配置时日报仍可用，只是没有新闻情绪分；Reddit 关注度不受影响。</p>
        </section>
      </div>

      <section className="ruled-section">
        <SectionHeading
          index="03"
          title="风控边界"
          note="桌面端只能收紧，不能放宽默认安全阈值。"
          action={<button className="secondary-button" disabled={busy !== null} onClick={() => void onSaveSettings()}><Save size={15} />保存全部设置</button>}
        />
        <div className="risk-grid">
          {([
            ["max_single_order_notional", "单笔金额上限 (USD)", 25, 10000],
            ["max_position_pct", "单一标的仓位上限 (%)", 1, 10],
            ["max_daily_turnover_pct", "日换手上限 (%)", 1, 25],
            ["max_daily_loss_pct", "日亏损熔断 (%)", 0.1, 1],
            ["minimum_analysis_score", "最低入场评分", 60, 100],
          ] as Array<[keyof RiskConfig, string, number, number]>).map(([field, label, min, max]) => (
            <label className="field-label" key={String(field)}>
              <span>{label}</span>
              <input
                type="number"
                min={min}
                max={max}
                step="any"
                value={String(settings.risk[field] ?? "")}
                onChange={(event) => onSettings({
                  ...settings,
                  risk: { ...settings.risk, [field]: Number(event.target.value) },
                })}
              />
              <small className="muted">允许范围 {min} – {max}</small>
            </label>
          ))}
        </div>
      </section>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<PageId>("dashboard");
  const [settings, setSettings] = useState<DesktopSettings>(defaultSettings);
  const [account, setAccount] = useState<LiveAccount | null>(null);
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null);
  const [cycle, setCycle] = useState<LiveCycleResult | null>(null);
  const [credentialCheck, setCredentialCheck] = useState<CredentialCheck | null>(null);
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [secretConfigured, setSecretConfigured] = useState(false);
  const [aiKeyConfigured, setAIKeyConfigured] = useState(false);
  const [alphaKeyConfigured, setAlphaKeyConfigured] = useState(false);
  const [busy, setBusy] = useState<BusyAction>("boot");
  const [toast, setToast] = useState<Toast | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const ready = keyConfigured && secretConfigured;

  // A briefing takes ~80s. Without a visible counter the window reads as hung.
  useEffect(() => {
    if (busy === null || busy === "boot") {
      setElapsed(0);
      return;
    }
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  const notify = useCallback((tone: Toast["tone"], message: string) => {
    setToast({ id: Date.now(), tone, message });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 5200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const loadAccount = useCallback(async (quiet = false) => {
    if (!quiet) setBusy("live-account");
    try {
      const value = await desktopBridge.liveAccount();
      setAccount(value);
      if (!quiet) {
        notify("success", `已读取账户：${value.positions.length} 个持仓，浮动盈亏 ${signed(value.unrealised_pnl_pct ?? 0)}%`);
      }
    } catch (error) {
      if (!quiet) notify("error", `读取账户失败：${asError(error)}`);
    } finally {
      if (!quiet) setBusy(null);
    }
  }, [notify]);

  useEffect(() => {
    let alive = true;
    const boot = async () => {
      try {
        const [nextSettings, hasKey, hasSecret, hasAI, hasAlpha] = await Promise.all([
          desktopBridge.loadSettings(),
          desktopBridge.keyStatus(),
          desktopBridge.secretStatus(),
          desktopBridge.aiKeyStatus(),
          desktopBridge.alphaVantageKeyStatus(),
        ]);
        if (!alive) return;
        setSettings(nextSettings);
        setKeyConfigured(hasKey);
        setSecretConfigured(hasSecret);
        setAIKeyConfigured(hasAI);
        setAlphaKeyConfigured(hasAlpha);
        if (hasKey && hasSecret) await loadAccount(true);
      } catch (error) {
        if (alive) notify("error", `初始化失败：${asError(error)}`);
      } finally {
        if (alive) setBusy(null);
      }
    };
    void boot();
    return () => { alive = false; };
  }, [notify, loadAccount]);

  const saveSettings = async (success = "设置已保存") => {
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

  const generateBriefing = async () => {
    setBusy("briefing");
    try {
      await desktopBridge.saveSettings(settings);
      const value = await desktopBridge.dailyBriefing(settings, {
        perSegment: 3,
        minimumScore: settings.risk.minimum_analysis_score,
      });
      setBriefing(value);
      const adds = value.ideas.filter((idea) => idea.action === "ADD").length;
      const trims = value.ideas.filter((idea) => idea.action === "TRIM").length;
      notify(
        value.ai_status === "error" ? "info" : "success",
        `日报已生成：${adds} 个建仓候选，${trims} 个减仓提示${value.ai_status === "ok" ? "（含 AI 综合）" : ""}`,
      );
    } catch (error) {
      notify("error", `生成日报失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const runCycle = async (confirmation: string, submit: boolean) => {
    setBusy(submit ? "live-submit" : "live-preview");
    try {
      await desktopBridge.saveSettings(settings);
      const value = await desktopBridge.runLiveCycle(settings, { confirmation, submit });
      setCycle(value);
      if (value.submitted) {
        notify("success", `已提交 ${value.executions.length} 笔订单，请立即对账确认成交`);
        await loadAccount(true);
      } else {
        notify("info", `预览完成：${value.approved_count}/${value.risk_decisions.length} 笔通过风控，未提交任何订单`);
      }
    } catch (error) {
      notify("error", `执行失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const reconcile = async () => {
    setBusy("reconcile");
    try {
      const value = await desktopBridge.liveReconcile();
      notify(
        value.unresolved.length > 0 ? "error" : "success",
        `对账完成：核实 ${value.checked} 笔，结清 ${value.settled.length}，挂单 ${value.still_open.length}，未解决 ${value.unresolved.length}`,
      );
      await loadAccount(true);
    } catch (error) {
      notify("error", `对账失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const cancelAll = async () => {
    setBusy("reconcile");
    try {
      await desktopBridge.liveCancelAll();
      notify("success", "已请求撤销全部挂单");
      await loadAccount(true);
    } catch (error) {
      notify("error", `撤单失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const testAI = async () => {
    setBusy("ai-test");
    try {
      await desktopBridge.saveSettings(settings);
      const result = await desktopBridge.testAIProvider(settings);
      if (result.status !== "ok") throw new Error(result.error ?? "未返回有效 JSON");
      notify("success", `${result.model} 连接成功，耗时 ${result.latency_ms} ms`);
    } catch (error) {
      notify("error", `AI 连接失败：${asError(error)}`);
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

  const verify = async () => {
    setBusy("verify");
    try {
      const value = await desktopBridge.verifyCredentials();
      setCredentialCheck(value);
      notify(value.ok ? "success" : "error", value.guidance);
    } catch (error) {
      notify("error", `自检失败：${asError(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const meta = pageMeta[page];
  const content = useMemo(() => {
    switch (page) {
      case "dashboard":
        return <Dashboard account={account} busy={busy} onRefresh={() => loadAccount(false)} goTo={setPage} />;
      case "briefing":
        return <BriefingPage briefing={briefing} aiConfigured={aiKeyConfigured && settings.research.ai_enabled} busy={busy} elapsed={elapsed} onGenerate={generateBriefing} goTo={setPage} />;
      case "strategy":
        return (
          <StrategyPage
            settings={settings}
            cycle={cycle}
            account={account}
            ready={ready}
            busy={busy}
            elapsed={elapsed}
            onSettings={setSettings}
            onSaveSettings={() => saveSettings("标的池已保存")}
            onPreview={() => runCycle("", false)}
            onSubmit={(confirmation) => runCycle(confirmation, true)}
            onReconcile={reconcile}
            onCancelAll={cancelAll}
            goTo={setPage}
          />
        );
      case "settings":
        return (
          <SettingsPage
            settings={settings}
            keyConfigured={keyConfigured}
            secretConfigured={secretConfigured}
            aiConfigured={aiKeyConfigured}
            alphaConfigured={alphaKeyConfigured}
            check={credentialCheck}
            busy={busy}
            onSettings={setSettings}
            onSaveSettings={() => saveSettings("设置已保存")}
            onSaveKey={async (value) => { setBusy("key"); try { await desktopBridge.saveKey(value); setKeyConfigured(true); notify("success", "API Key 已存入钥匙串"); } catch (error) { notify("error", asError(error)); throw error; } finally { setBusy(null); } }}
            onDeleteKey={async () => { setBusy("key"); try { await desktopBridge.deleteKey(); setKeyConfigured(false); notify("success", "API Key 已删除"); } catch (error) { notify("error", asError(error)); } finally { setBusy(null); } }}
            onSaveSecret={async (value) => { setBusy("secret"); try { await desktopBridge.saveSecret(value); setSecretConfigured(true); notify("success", "Secret 已存入钥匙串"); } catch (error) { notify("error", asError(error)); throw error; } finally { setBusy(null); } }}
            onDeleteSecret={async () => { setBusy("secret"); try { await desktopBridge.deleteSecret(); setSecretConfigured(false); setAccount(null); notify("success", "Secret 已删除"); } catch (error) { notify("error", asError(error)); } finally { setBusy(null); } }}
            onSaveAIKey={async (value) => { setBusy("ai-key"); try { await desktopBridge.saveAIKey(value); setAIKeyConfigured(true); notify("success", "AI Token 已存入钥匙串"); } catch (error) { notify("error", asError(error)); throw error; } finally { setBusy(null); } }}
            onDeleteAIKey={async () => { setBusy("ai-key"); try { await desktopBridge.deleteAIKey(); setAIKeyConfigured(false); notify("success", "AI Token 已删除"); } catch (error) { notify("error", asError(error)); } finally { setBusy(null); } }}
            onSaveAlphaKey={async (value) => { setBusy("alpha-key"); try { await desktopBridge.saveAlphaVantageKey(value); setAlphaKeyConfigured(true); notify("success", "Alpha Vantage Key 已存入钥匙串"); } catch (error) { notify("error", asError(error)); throw error; } finally { setBusy(null); } }}
            onDeleteAlphaKey={async () => { setBusy("alpha-key"); try { await desktopBridge.deleteAlphaVantageKey(); setAlphaKeyConfigured(false); notify("success", "Alpha Vantage Key 已删除"); } catch (error) { notify("error", asError(error)); } finally { setBusy(null); } }}
            onVerify={verify}
            onTestAI={testAI}
            onAcceptDisclaimer={acceptDisclaimer}
          />
        );
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, account, briefing, cycle, settings, busy, elapsed, ready, keyConfigured, secretConfigured, aiKeyConfigured, alphaKeyConfigured, credentialCheck]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><span /><i /></div>
          <div><strong>BerkshireNexus</strong><span>AI 产业链交易台</span></div>
        </div>
        <nav aria-label="主要导航">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={`nav-item ${page === item.id ? "active" : ""}`}
                onClick={() => setPage(item.id)}
              >
                <Icon size={17} aria-hidden="true" />
                <div><strong>{item.label}</strong><span>{item.description}</span></div>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <div className={`sidebar-status ${ready ? "live" : ""}`}>
            <span aria-hidden="true" />
            <div>
              <strong>{ready ? "实盘就绪" : "凭证待配置"}</strong>
              <span>{account ? `净资产 ${money.format(account.net_worth ?? account.equity)}` : "未读取账户"}</span>
            </div>
          </div>
          <span className="mono muted">LOCAL-FIRST · v2.0</span>
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
            {busy !== null && busy !== "boot" && (
              <div className="running-chip" role="status">
                <LoaderCircle className="spin" size={13} />
                <span>{TASK_LABEL[busy] ?? "处理中"} · {elapsed}s</span>
              </div>
            )}
            <button
              className="icon-button"
              aria-label="刷新账户"
              title="刷新账户"
              disabled={blocked(busy, "live-account") || !ready}
              onClick={() => void loadAccount(false)}
            >
              <RefreshCw className={busy === "live-account" ? "spin" : ""} size={17} />
            </button>
          </div>
        </header>
        <div className="content-scroll">{busy === "boot" ? <LoadingPage /> : content}</div>
      </main>

      {toast && (
        <div className={`toast toast-${toast.tone}`} role="status" key={toast.id}>
          {toast.tone === "success" ? <CircleCheck size={18} /> : toast.tone === "error" ? <CircleAlert size={18} /> : <Activity size={18} />}
          <span>{toast.message}</span>
          <button aria-label="关闭提示" onClick={() => setToast(null)}><X size={15} /></button>
        </div>
      )}
    </div>
  );
}
