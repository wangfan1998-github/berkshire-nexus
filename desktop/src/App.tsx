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
};

/** Actions that must not overlap: they mutate credentials, orders or state. */
const EXCLUSIVE: ReadonlySet<string> = new Set([
  "boot", "live-submit", "reconcile", "disclaimer",
  "key", "secret", "ai-key",
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

/** Sparkline of 1y closes. Colour follows first-to-last direction. */
function Sparkline({
  points,
  low,
  high,
  width = 132,
  height = 34,
}: {
  points: Array<{ t: number; c: number }>;
  low?: number;
  high?: number;
  width?: number;
  height?: number;
}) {
  if (points.length < 2) return <span className="muted">—</span>;
  const values = points.map((p) => p.c);
  // Anchor the scale to the 52-week range when known, so the line shows where
  // price sits in its range rather than filling the box regardless.
  const min = Math.min(...values, low && low > 0 ? low : Infinity);
  const max = Math.max(...values, high && high > 0 ? high : -Infinity);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(height - ((p.c - min) / span) * height).toFixed(1)}`)
    .join(" ");
  const rising = values[values.length - 1] >= values[0];
  const stroke = rising ? "var(--green)" : "var(--risk)";
  const lastY = height - ((values[values.length - 1] - min) / span) * height;
  return (
    <svg className="sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="一年走势">
      <path d={`${path} L${width},${height} L0,${height} Z`} fill={stroke} opacity="0.08" />
      <path d={path} fill="none" stroke={stroke} strokeWidth="1.4" />
      <circle cx={width} cy={lastY} r="2" fill={stroke} />
    </svg>
  );
}

interface Slice {
  ticker: string;
  weight_pct: number;
  value?: number;
  pnl?: number;
  return_pct?: number;
}

/** Polar point on a circle, in SVG coordinates. */
function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const a = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
}

/** Donut arc as a filled ring segment, so slices can be offset individually. */
function arcPath(cx: number, cy: number, rOuter: number, rInner: number, from: number, to: number) {
  // A single arc cannot express a full circle; nudge it so 100% still renders.
  const sweep = Math.min(to - from, 359.99);
  const end = from + sweep;
  const o1 = polar(cx, cy, rOuter, from);
  const o2 = polar(cx, cy, rOuter, end);
  const i2 = polar(cx, cy, rInner, end);
  const i1 = polar(cx, cy, rInner, from);
  const large = sweep > 180 ? 1 : 0;
  return [
    `M${o1.x.toFixed(2)},${o1.y.toFixed(2)}`,
    `A${rOuter},${rOuter} 0 ${large} 1 ${o2.x.toFixed(2)},${o2.y.toFixed(2)}`,
    `L${i2.x.toFixed(2)},${i2.y.toFixed(2)}`,
    `A${rInner},${rInner} 0 ${large} 0 ${i1.x.toFixed(2)},${i1.y.toFixed(2)}`,
    "Z",
  ].join(" ");
}

/**
 * Interactive allocation donut.
 *
 * Hovering a slice or legend row lifts the slice and shows its detail in the
 * centre, so the numbers are readable without a wall of legend text.
 */
function Donut({
  rows,
  size = 180,
  title,
  onHover,
  activeTicker,
}: {
  rows: Slice[];
  size?: number;
  title?: string;
  onHover?: (ticker: string | null) => void;
  activeTicker?: string | null;
}) {
  const [internal, setInternal] = useState<string | null>(null);
  const active = activeTicker !== undefined ? activeTicker : internal;
  const setActive = (value: string | null) => {
    setInternal(value);
    onHover?.(value);
  };

  const shown = rows.filter((r) => r.weight_pct > 0.01);
  if (shown.length === 0) return <span className="muted">—</span>;

  const cx = size / 2;
  const cy = size / 2;
  const rOuter = size / 2 - 12;
  const rInner = rOuter * 0.62;
  const total = shown.reduce((sum, r) => sum + r.weight_pct, 0) || 100;

  let cursor = 0;
  const slices = shown.map((row, index) => {
    const sweep = (row.weight_pct / total) * 360;
    const from = cursor;
    cursor += sweep;
    return { row, from, to: from + sweep, index, mid: from + sweep / 2 };
  });

  const focused = slices.find((s) => s.row.ticker === active);
  const centre = focused?.row;

  return (
    <div className="donut-wrap" style={{ width: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={title ?? "组合占比"}
        onMouseLeave={() => setActive(null)}
      >
        {slices.map(({ row, from, to, index, mid }) => {
          const isActive = row.ticker === active;
          // Lift the hovered slice outward along its own bisector.
          const shift = isActive ? 4 : 0;
          const offset = polar(0, 0, shift, mid);
          return (
            <path
              key={row.ticker}
              d={arcPath(cx, cy, rOuter, rInner, from, to)}
              transform={`translate(${offset.x.toFixed(2)},${offset.y.toFixed(2)})`}
              fill={sliceColor(row.ticker, index)}
              opacity={active && !isActive ? 0.32 : 1}
              className="donut-slice"
              onMouseEnter={() => setActive(row.ticker)}
              onFocus={() => setActive(row.ticker)}
              tabIndex={0}
            >
              <title>{`${row.ticker} ${row.weight_pct.toFixed(2)}%`}</title>
            </path>
          );
        })}
      </svg>
      <div className="donut-centre" aria-live="polite">
        {centre ? (
          <>
            <strong className="mono">{centre.ticker}</strong>
            <span className="donut-centre-pct">{centre.weight_pct.toFixed(2)}%</span>
            {centre.value !== undefined && (
              <span className="muted">{money.format(centre.value)}</span>
            )}
            {centre.return_pct !== undefined && centre.ticker !== "CASH" && (
              <span className={centre.return_pct >= 0 ? "pnl-up" : "pnl-down"}>
                {signed(centre.return_pct)}%
              </span>
            )}
          </>
        ) : (
          <>
            <strong>{shown.length}</strong>
            <span className="muted">{title ?? "项持仓"}</span>
          </>
        )}
      </div>
    </div>
  );
}

function sliceColor(ticker: string, index: number) {
  if (ticker === "CASH") return "var(--line-dark)";
  return SLICE_COLORS[index % SLICE_COLORS.length];
}

// Ordered for adjacent-slice contrast, and checked to stay legible against the
// paper background at small sizes.
const SLICE_COLORS = [
  "#3f6b52", "#c08b3e", "#4a7196", "#8c5f7d", "#b06a4c",
  "#6f9b7a", "#d9b166", "#7fa2c2", "#a98aa6", "#c98d72",
  "#2c5240", "#8a6a2e",
];

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
  // Shared between chart and legend so hovering either highlights both.
  const [hovered, setHovered] = useState<string | null>(null);

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
  const donutRows: Slice[] = [
    ...account.positions
      .filter((item) => item.market_value > 0.01)
      .map((item) => ({
        ticker: item.ticker,
        weight_pct: item.weight_pct,
        value: item.market_value,
        pnl: item.unrealised_pnl,
        return_pct: item.return_pct,
      })),
    ...(account.cash > 0.01
      ? [{
          ticker: "CASH",
          weight_pct: (account.cash / Math.max(account.equity, 1)) * 100,
          value: account.cash,
        }]
      : []),
  ].sort((a, b) => b.weight_pct - a.weight_pct);

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
          title="组合构成与持仓"
          note="金额单位 USD。成本价由成交记录推导（Binance 无成本价接口）。hover 饼图或表格行可联动高亮，点击表头可排序。"
          action={
            <button className="secondary-button" disabled={blocked(busy, "live-account")} onClick={() => void onRefresh()}>
              {busy === "live-account" ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}刷新
            </button>
          }
        />
        <div className="donut-row">
          <Donut rows={donutRows} activeTicker={hovered} onHover={setHovered} title="项持仓" />
          <div className="donut-side">
            <div className="metric-row compact">
              <div><span>股票市值</span><strong>{money.format(account.holdings_value)}</strong></div>
              <div><span>现金</span><strong>{money.format(account.cash)}</strong></div>
              <div><span>浮动盈亏</span><strong className={unrealised >= 0 ? "pnl-up" : "pnl-down"}>{signed(unrealisedPct)}%</strong></div>
            </div>
          </div>
        </div>
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
                  <tr
                    key={position.ticker}
                    className={hovered === position.ticker ? "legend-active" : hovered ? "legend-dim" : ""}
                    onMouseEnter={() => setHovered(position.ticker)}
                    onMouseLeave={() => setHovered(null)}
                  >
                    <td className="mono">
                      <i className="legend-dot" style={{ background: sliceColor(position.ticker, donutRows.findIndex((r) => r.ticker === position.ticker)) }} />
                      {position.ticker}
                      {position.tokenized ? <span className="muted"> ·b</span> : null}
                      {position.cost_complete === false ? <span className="muted" title="部分成交早于查询窗口，成本不完整"> *</span> : null}
                    </td>
                    <td>{position.quantity.toFixed(4)}</td>
                    <td>{known ? plain.format(position.average_cost ?? 0) : "—"}</td>
                    <td>
                      {position.price ? plain.format(position.price) : "—"}
                      {position.price_source === "binance-stream" && position.market_phase && (
                        <span className="phase-tag" title="Binance 实时成交价">{position.market_phase}</span>
                      )}
                      {position.price_source === "market-close" && (
                        <span className="spread-flag" title={`Binance 盘后买卖价差 ${position.spread_pct?.toFixed(2)}%，已改用交易所收盘价`}>*</span>
                      )}
                      {position.price_unreliable && (
                        <span className="spread-flag" title={`买卖价差 ${position.spread_pct?.toFixed(2)}%，且无法取得交易所价格，此价为估算`}>~</span>
                      )}
                    </td>
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
        {account.positions.some((p) => p.price_source === "binance-stream") && (
          <p className="muted-note">
            带盘口阶段标记的标的使用 Binance 实时成交价。行情流按符号轮播推送，
            未覆盖到的标的先用其他来源，多刷新几次会逐步补全。
          </p>
        )}
        {account.positions.some((p) => p.price_source === "market-close") && (
          <p className="muted-note">
            * 标记的标的在 Binance 盘后买卖价差过大（挂单稀疏），已改用交易所实际收盘价计算。
            开盘后价差收窄会自动切回 Binance 报价。
          </p>
        )}
        {account.positions.some((p) => p.price_unreliable) && (
          <p className="warn-note">
            ~ 标记的标的价差过大且取不到交易所价格，该现价为估算值，市值与收益率会有偏差。
          </p>
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
  onExecute,
  goTo,
}: {
  briefing: DailyBriefing | null;
  aiConfigured: boolean;
  busy: BusyAction;
  elapsed: number;
  onGenerate: () => Promise<void>;
  onExecute: (tickers: string[]) => void;
  goTo: (page: PageId) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  // Only ADD and TRIM produce orders; HOLD and AVOID are informational.
  const actionable = (briefing?.ideas ?? []).filter(
    (idea) => idea.action === "ADD" || idea.action === "TRIM",
  );

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
                    <div className="idea-main">
                      <div className="idea-id">
                        <strong className="mono">{idea.ticker}</strong>
                        <StatusMark tone={ACTION_TONE[idea.action] ?? "neutral"}>{ACTION_LABEL[idea.action] ?? idea.action}</StatusMark>
                        {idea.buzz_crowded && <span className="crowded-tag" title={idea.buzz_note}>拥挤</span>}
                      </div>
                      <span className="idea-segment muted">{idea.segment_label}</span>
                    </div>

                    {/* Direct grid children so all rows share one set of column
                        tracks; always rendered so an absent value cannot shift
                        the columns after it. */}
                    <span className="idea-cell">
                      <em className="idea-cap">分</em>
                      <strong>{idea.score.toFixed(1)}</strong>
                    </span>
                    <span className="idea-cell">
                      <em className="idea-cap">动量</em>
                      <strong>{idea.momentum_score.toFixed(1)}</strong>
                    </span>
                    <span className="idea-cell">
                      <em className="idea-cap">现价</em>
                      <strong>
                        {money.format(idea.price)}
                        <i className={idea.change_pct >= 0 ? "pnl-up" : "pnl-down"}>{signed(idea.change_pct)}%</i>
                      </strong>
                    </span>
                    <span className="idea-cell">
                      <em className="idea-cap">成本</em>
                      {idea.held_quantity > 0 ? (
                        <strong>
                          {money.format(idea.average_cost)}
                          <i className={idea.unrealised_pct >= 0 ? "pnl-up" : "pnl-down"}>{signed(idea.unrealised_pct, 1)}%</i>
                        </strong>
                      ) : <strong className="muted">未持仓</strong>}
                    </span>

                    <Sparkline points={idea.price_history ?? []} low={idea.fifty_two_week_low} high={idea.fifty_two_week_high} width={92} height={28} />
                    <ChevronRight size={14} className={`idea-chevron ${expanded === idea.ticker ? "rotated" : ""}`} />
                  </button>
                  {expanded === idea.ticker && (
                    <div className="idea-body">
                      <p><strong>判定依据</strong></p>
                      <ul>{idea.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
                      {idea.fifty_two_week_high > idea.fifty_two_week_low && (
                        <>
                          <p><strong>一年走势</strong></p>
                          <div className="chart-row">
                            <Sparkline points={idea.price_history ?? []} low={idea.fifty_two_week_low} high={idea.fifty_two_week_high} width={260} height={56} />
                            <div className="range-meta">
                              <span>52周低 {money.format(idea.fifty_two_week_low)}</span>
                              <span>现价 {money.format(idea.price)}</span>
                              <span>52周高 {money.format(idea.fifty_two_week_high)}</span>
                              <span className="muted">
                                区间分位 {(((idea.price - idea.fifty_two_week_low) / (idea.fifty_two_week_high - idea.fifty_two_week_low)) * 100).toFixed(0)}%
                              </span>
                            </div>
                          </div>
                        </>
                      )}
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
              <button
                className="primary-button"
                disabled={actionable.length === 0}
                onClick={() => onExecute(actionable.map((idea) => idea.ticker))}
              >
                把 {actionable.length} 个可执行标的送去策略页 <ArrowRight size={15} />
              </button>
              {actionable.length === 0 && (
                <span className="muted">本轮没有 建仓/减仓 标的，无需执行</span>
              )}
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
  onRedeemEarn,
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
  onRedeemEarn: (productId: string, shortfall: number, confirmation: string) => Promise<void>;
  goTo: (page: PageId) => void;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [allocHover, setAllocHover] = useState<string | null>(null);
  const joined = settings.universe.join(", ");
  const [universeText, setUniverseText] = useState(joined);
  // Keep the field in step with the universe that was handed in, while leaving
  // in-progress manual edits alone.
  const [syncedFrom, setSyncedFrom] = useState(joined);
  useEffect(() => {
    if (joined !== syncedFrom) {
      setUniverseText(joined);
      setSyncedFrom(joined);
    }
  }, [joined, syncedFrom]);
  const acknowledged = confirmation.trim() === LIVE_ACKNOWLEDGEMENT;
  const approved = cycle?.risk_decisions.filter((item) => item.approved) ?? [];
  // Only rows that actually move, so the table stays about the change.
  const allocDelta = (() => {
    const alloc = cycle?.allocation;
    if (!alloc) return [] as Array<{ ticker: string; before: number; after: number; delta: number }>;
    const before = new Map(alloc.before.map((r) => [r.ticker, r.weight_pct]));
    const after = new Map(alloc.after.map((r) => [r.ticker, r.weight_pct]));
    return [...new Set([...before.keys(), ...after.keys()])]
      .map((ticker) => {
        const b = before.get(ticker) ?? 0;
        const a = after.get(ticker) ?? 0;
        return { ticker, before: b, after: a, delta: a - b };
      })
      .filter((row) => Math.abs(row.delta) > 0.01)
      .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  })();

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
          note="策略只会对这里列出的标的下单。可从日报页一键带入，也可手动编辑（逗号或空格分隔）。"
          action={
            <button className="secondary-button" disabled={busy !== null} onClick={() => { commitUniverse(); void onSaveSettings(); }}>
              <Save size={15} />保存
            </button>
          }
        />
        <label className="field-label">
          <span>UNIVERSE（{settings.universe.length} 个标的）</span>
          <input
            value={universeText}
            onChange={(event) => setUniverseText(event.target.value)}
            onBlur={commitUniverse}
            placeholder="先去日报页生成，或手动输入 AAPL, NVDA, TSM"
            spellCheck={false}
          />
        </label>
        {settings.universe.length === 0 && (
          <p className="warn-note">
            标的池为空。请先到日报页「生成日报」，或在上面手动输入代码。
          </p>
        )}
        <p className="muted-note">单笔上限 {money.format(settings.risk.max_single_order_notional)} · 单一标的上限 {settings.risk.max_position_pct}% · 可在设置页调整</p>
        <ol className="flow-steps">
          <li><strong>预览（不下单）</strong>：跑一遍研究→取价→风控，只显示会下什么单，不发给交易所。</li>
          <li>看下方「预览结果」确认方向、数量、限价、以及被风控拒绝的原因。</li>
          <li>确认无误后，在下面输入确认短语，再点<strong>提交真实订单</strong>。</li>
          <li>提交后<strong>立即点「对账」</strong>——交易所回执只代表已挂单，不代表成交。</li>
        </ol>
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
          {cycle.cash_plan && cycle.cash_plan.needed_for_buys > 0 && (
            <div className={cycle.cash_plan.shortfall > 0 ? "warn-note" : "muted-note"}>
              <strong>买入资金</strong>：需要 {money.format(cycle.cash_plan.needed_for_buys)}，
              当前可用 {money.format(cycle.cash_plan.spendable_usdc)} USDC
              （CARD {money.format(cycle.cash_plan.card_usdc)} · MAIN {money.format(cycle.cash_plan.main_usdc)}）
              {cycle.cash_plan.in_earn_usdc > 0.01 && `，理财中 ${money.format(cycle.cash_plan.in_earn_usdc)}`}
              {cycle.cash_plan.shortfall > 0 && (
                <>
                  ，<strong>缺口 {money.format(cycle.cash_plan.shortfall)}</strong>
                  <br />{cycle.cash_plan.advice}
                  {/* Earn can cover it, so offer the redemption instead of
                      leaving the operator to do it in the Binance app. */}
                  {cycle.cash_plan.earn_product_id &&
                    cycle.cash_plan.in_earn_usdc >= cycle.cash_plan.shortfall && (
                      <>
                        <br />
                        <button
                          className="secondary-button"
                          disabled={blocked(busy, "reconcile") || !acknowledged}
                          onClick={() =>
                            void onRedeemEarn(
                              cycle.cash_plan!.earn_product_id,
                              cycle.cash_plan!.shortfall,
                              confirmation.trim(),
                            )
                          }
                        >
                          {busy === "reconcile" ? (
                            <LoaderCircle className="spin" size={15} />
                          ) : (
                            <WalletCards size={15} />
                          )}
                          赎回 {money.format(cycle.cash_plan.shortfall)} 到 CARD
                        </button>
                        {!acknowledged && (
                          <span className="muted-note">
                            　赎回会动用真实资金，需先填写上方确认短语
                          </span>
                        )}
                      </>
                    )}
                </>
              )}
            </div>
          )}
          {cycle.dropped_orders && cycle.dropped_orders.length > 0 && (
            <p className="muted-note">
              因换手预算丢弃 {cycle.dropped_orders.length} 笔：
              {cycle.dropped_orders.map((row) => `${row.ticker} ${row.side} ${money.format(row.notional)}`).join("、")}
            </p>
          )}
          {cycle.unpriced_positions && cycle.unpriced_positions.length > 0 && (
            <p className="warn-note">以下持仓取不到报价，权益被低估，实盘提交已被拒绝：{cycle.unpriced_positions.join("、")}</p>
          )}
          {cycle.allocation && cycle.allocation.after.length > 0 && (
            <div className="alloc-compare">
              <div>
                <span className="alloc-label">调整前</span>
                <Donut rows={cycle.allocation.before} size={150} activeTicker={allocHover} onHover={setAllocHover} title="项" />
              </div>
              <ArrowRight size={18} className="alloc-arrow" />
              <div>
                <span className="alloc-label">调整后（仅计入通过风控的订单）</span>
                <Donut rows={cycle.allocation.after} size={150} activeTicker={allocHover} onHover={setAllocHover} title="项" />
              </div>
              <table className="data-table numeric-table alloc-table">
                <thead><tr><th>标的</th><th>前 %</th><th>后 %</th><th>变化</th></tr></thead>
                <tbody>
                  {allocDelta.map((row) => (
                    <tr
                      key={row.ticker}
                      className={allocHover === row.ticker ? "legend-active" : allocHover ? "legend-dim" : ""}
                      onMouseEnter={() => setAllocHover(row.ticker)}
                      onMouseLeave={() => setAllocHover(null)}
                    >
                      <td className="mono">{row.ticker}</td>
                      <td>{row.before.toFixed(2)}</td>
                      <td>{row.after.toFixed(2)}</td>
                      <td className={row.delta >= 0 ? "pnl-up" : "pnl-down"}>{signed(row.delta)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
  onVerify,
  onTestAI,
  onAcceptDisclaimer,
}: {
  settings: DesktopSettings;
  keyConfigured: boolean;
  secretConfigured: boolean;
  aiConfigured: boolean;
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
  onVerify: () => Promise<void>;
  onTestAI: () => Promise<void>;
  onAcceptDisclaimer: () => Promise<void>;
}) {
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const [aiKey, setAIKey] = useState("");
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

          <SectionHeading index="03" title="情绪数据源" note="全部免费无需 Key：Reddit 关注度取自 ApeWisdom，新闻情绪由 Google News 头条交给上方配置的模型打分。" />
          <p className="muted-note">
            新闻情绪覆盖每个分析标的，并计入综合分的时效层。原先的 Alpha Vantage 免费额度为 25 次/天，
            不足以覆盖一次完整扫描，已于 2026-08-31 移除。
          </p>
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
        const [nextSettings, hasKey, hasSecret, hasAI] = await Promise.all([
          desktopBridge.loadSettings(),
          desktopBridge.keyStatus(),
          desktopBridge.secretStatus(),
          desktopBridge.aiKeyStatus(),
        ]);
        if (!alive) return;
        setSettings(nextSettings);
        setKeyConfigured(hasKey);
        setSecretConfigured(hasSecret);
        setAIKeyConfigured(hasAI);
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

  /** Carry the briefing's actionable picks into the strategy universe. */
  const sendToStrategy = (tickers: string[]) => {
    if (tickers.length === 0) return;
    const next = { ...settings, universe: tickers };
    setSettings(next);
    // Persist so the Python side sees the same list on the next invocation.
    void desktopBridge.saveSettings(next).catch(() => undefined);
    setCycle(null);
    setPage("strategy");
    notify("info", `已带入 ${tickers.length} 个标的：${tickers.join("、")}。请先点「预览（不下单）」`);
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
      const actionable = value.ideas
        .filter((idea) => idea.action === "ADD" || idea.action === "TRIM")
        .map((idea) => idea.ticker);
      if (actionable.length > 0) {
        const next = { ...settings, universe: actionable };
        setSettings(next);
        void desktopBridge.saveSettings(next).catch(() => undefined);
        setCycle(null);
      }
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

  /**
   * Redeem exactly the shortfall from Simple Earn into CARD.
   *
   * Binance does not auto-redeem, so an Earn balance can never fund a BUY —
   * without this the cycle just reports "现金不足" with no way to act on it.
   * A small buffer is added because redemption and the order are separate
   * requests and the price can tick up between them.
   */
  const redeemEarn = async (productId: string, shortfall: number, confirmation: string) => {
    setBusy("reconcile");
    try {
      const amount = Math.ceil((shortfall + 1) * 100) / 100;
      await desktopBridge.liveRedeemEarn({ productId, amount, redeemAll: false, confirmation });
      notify("success", `已请求赎回 ${amount.toFixed(2)} USDC，到账后请重新预览`);
      await loadAccount(true);
    } catch (error) {
      notify("error", `赎回失败：${asError(error)}`);
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
        return <BriefingPage briefing={briefing} aiConfigured={aiKeyConfigured && settings.research.ai_enabled} busy={busy} elapsed={elapsed} onGenerate={generateBriefing} onExecute={sendToStrategy} goTo={setPage} />;
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
            onRedeemEarn={redeemEarn}
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
            onVerify={verify}
            onTestAI={testAI}
            onAcceptDisclaimer={acceptDisclaimer}
          />
        );
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, account, briefing, cycle, settings, busy, elapsed, ready, keyConfigured, secretConfigured, aiKeyConfigured, credentialCheck]);

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
