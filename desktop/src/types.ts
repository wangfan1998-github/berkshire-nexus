export type PageId =
  | "overview"
  | "research"
  | "ai"
  | "portfolio"
  | "agent"
  | "models"
  | "risk"
  | "audit"
  | "settings";

export interface Holding {
  ticker: string;
  quantity: number;
  price: number;
  market_value: number;
  weight_pct: number;
}

export interface Execution {
  recorded_at_utc?: string;
  ticker: string;
  side: "BUY" | "SELL";
  status: string;
  filled_quantity: number;
  average_price: number;
  fee: number;
  message?: string;
}

export interface AuditSummary {
  path: string;
  name: string;
  generated_at_utc?: string;
  order_count: number;
  execution_count: number;
  analysis_count: number;
  champion_version?: string | null;
}

export interface ModelArtifact {
  version: string;
  trained_at_utc: string;
  training_sample_count: number;
  validation_metrics: {
    directional_accuracy: number;
    rmse: number;
    sample_count: number;
  };
  model: {
    feature_names: string[];
    weights: Record<string, number>;
    intercept: number;
  };
}

export interface RiskConfig {
  minimum_analysis_score: number;
  max_position_pct: number;
  max_single_order_notional: number;
  max_daily_turnover_pct: number;
  max_daily_loss_pct: number;
  allowed_symbols: string[];
}

export type AIProvider = "openai-compatible" | "ollama" | "codex-cli";

export interface ResearchConfig {
  market_provider: "yahoo-nasdaq";
  news_enabled: boolean;
  news_provider: "yahoo" | "yahoo-google";
  max_news_items: number;
  ai_enabled: boolean;
  ai_provider: AIProvider;
  ai_model: string;
  ai_base_url: string;
  ai_timeout_seconds: number;
  ai_temperature: number;
  ai_reasoning_effort: "none" | "minimal" | "low" | "medium" | "high" | "xhigh";
}

export interface DesktopSettings {
  universe: string[];
  interval_minutes: number;
  initial_cash: number;
  auto_promote_paper: boolean;
  risk: RiskConfig;
  research: ResearchConfig;
}

export interface AppSnapshot {
  generated_at_utc: string;
  demo?: boolean;
  portfolio: {
    cash: number;
    equity: number;
    holdings_value: number;
    holdings: Holding[];
    start_of_day_equity: number;
    daily_traded_notional: number;
    trading_date: string;
  };
  learning: {
    snapshot_count: number;
    observation_count: number;
    minimum_training_samples: number;
    champion: ModelArtifact | null;
    challenger: ModelArtifact | null;
  };
  risk: Omit<RiskConfig, "allowed_symbols"> & {
    minimum_order_notional: number;
    allow_market_orders_live: boolean;
    require_verified_data_live: boolean;
  };
  agent: {
    running: boolean;
    state: string;
    cycles_completed: number;
    tickers?: string[];
    interval_minutes?: number;
    last_cycle_at_utc?: string;
    last_error?: string | null;
  };
  executions: Execution[];
  audits: AuditSummary[];
  last_cycle: {
    generated_at_utc?: string;
    analyses: Array<{
      ticker: string;
      score: number;
      recommendation: string;
      data_source: string;
      uses_fallback_data: boolean;
    }>;
    orders: unknown[];
    executions: Execution[];
    champion_version?: string | null;
  } | null;
}

export interface AnalysisReport {
  analysis_id: string;
  generated_at_utc: string;
  ticker: string;
  name: string;
  sector: string;
  price: number;
  pe: number;
  beta: number;
  score: number;
  recommendation: string;
  data_source: string;
  uses_fallback_data: boolean;
  as_of_utc: string;
  currency: string;
  exchange: string;
  market_status: string;
  previous_close: number;
  price_change_pct: number;
  quote_as_of_utc: string;
  fundamentals_as_of: string;
  verification_level: "third-party-complete" | "third-party-degraded" | "offline-fallback" | string;
  is_authoritative: boolean;
  market_data_age_seconds: number | null;
  fallback_fields: string[];
  source_trace: Array<{
    provider: string;
    kind: string;
    status: string;
    as_of_utc: string;
    retrieved_at_utc: string;
    latency_ms: number;
    fields: string[];
    message: string;
  }>;
  chokepoint: Record<string, unknown> & {
    chokepoint_level: number;
    overall_score: number;
    chokepoint_title: string;
  };
  masters: Record<string, unknown> & {
    consensus_score: number;
    consensus_verdict: string;
    mirror_test_summary: string;
    munger_inversion_summary: string;
  };
  valuation: Record<string, unknown> & {
    margin_of_safety_pct: number;
    intrinsic_value_dcf: number;
    valuation_status: string;
  };
  quant: Record<string, unknown> & {
    quality_score: number;
    value_score: number;
    growth_score: number;
    momentum_score: number;
    risk_adjusted_score: number;
  };
  risk: Record<string, unknown> & {
    recommended_max_allocation_pct: number;
    stop_loss_trigger_pct: number;
    portfolio_role: string;
    redline_failure_criteria: string[];
  };
  news: {
    status: "ok" | "degraded" | "empty" | "error" | "disabled";
    items: Array<{
      evidence_id: string;
      ticker: string;
      title: string;
      url: string;
      publisher: string;
      published_at_utc: string;
      retrieved_at_utc: string;
      source: string;
      related_tickers: string[];
      content_hash: string;
    }>;
    providers_attempted: string[];
    retrieved_at_utc: string;
    latency_ms: number;
    error?: string | null;
  };
  ai_research: {
    status: "ok" | "error" | "disabled";
    provider: AIProvider;
    model: string;
    prompt_version: string;
    generated_at_utc: string;
    latency_ms: number;
    summary: string;
    thesis: string;
    catalysts: string[];
    risks: string[];
    action_bias: "BULLISH" | "NEUTRAL" | "BEARISH" | "INSUFFICIENT_EVIDENCE";
    confidence: number;
    citations: string[];
    usage: Record<string, unknown>;
    error?: string | null;
  };
}

export interface AgentRuntimeStatus {
  running: boolean;
  pid?: number | null;
  status: AppSnapshot["agent"];
}
