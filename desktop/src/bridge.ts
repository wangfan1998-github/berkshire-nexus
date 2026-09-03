import { invoke } from "@tauri-apps/api/core";
import { defaultSettings, mockReports, mockSnapshot } from "./mock";
import type {
  AgentRuntimeStatus,
  AnalysisReport,
  AppSnapshot,
  CredentialCheck,
  DesktopSettings,
  DailyBriefing,
  LiveAccount,
  LiveCycleResult,
  ScreenResult,
  SectorOverview,
  SectorConstituents,
  TickerSearchResult,
  LiveReconciliation,
} from "./types";

const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
const wait = (milliseconds = 350) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export const desktopBridge = {
  isTauri,

  async snapshot(): Promise<AppSnapshot> {
    if (isTauri) return invoke<AppSnapshot>("app_snapshot");
    await wait();
    return structuredClone(mockSnapshot);
  },

  async analyzeWithSettings(tickers: string[], settings: DesktopSettings): Promise<AnalysisReport[]> {
    if (isTauri) {
      const value = await invoke<{ reports: AnalysisReport[] }>("analyze_tickers", {
        tickers,
        researchConfig: settings.research,
      });
      return value.reports;
    }
    await wait(700);
    return mockReports.filter((report) => tickers.includes(report.ticker));
  },

  async runCycle(settings: DesktopSettings): Promise<AppSnapshot> {
    if (isTauri) {
      const value = await invoke<{ snapshot: AppSnapshot }>("run_paper_cycle", {
        tickers: settings.universe,
        initialCash: settings.initial_cash,
        autoPromotePaper: settings.auto_promote_paper,
        riskConfig: settings.risk,
        researchConfig: settings.research,
      });
      return value.snapshot;
    }
    await wait(900);
    return { ...structuredClone(mockSnapshot), generated_at_utc: new Date().toISOString() };
  },

  async startAgent(settings: DesktopSettings): Promise<void> {
    if (isTauri) {
      await invoke("start_agent", {
        tickers: settings.universe,
        options: {
          interval_minutes: settings.interval_minutes,
          initial_cash: settings.initial_cash,
          auto_promote_paper: settings.auto_promote_paper,
          risk_config: settings.risk,
          research_config: settings.research,
        },
      });
      return;
    }
    await wait();
  },

  async stopAgent(): Promise<void> {
    if (isTauri) await invoke("stop_agent");
    else await wait();
  },

  async agentStatus(): Promise<AgentRuntimeStatus> {
    if (isTauri) return invoke<AgentRuntimeStatus>("agent_runtime_status");
    return { running: false, pid: null, status: mockSnapshot.agent };
  },

  async loadSettings(): Promise<DesktopSettings> {
    if (isTauri) {
      const stored = await invoke<Partial<DesktopSettings>>("load_desktop_settings");
      return {
        ...defaultSettings,
        ...stored,
        risk: { ...defaultSettings.risk, ...(stored.risk ?? {}) },
        research: { ...defaultSettings.research, ...(stored.research ?? {}) },
      };
    }
    const stored = localStorage.getItem("berkshire-nexus-settings");
    if (!stored) return structuredClone(defaultSettings);
    const parsed = JSON.parse(stored) as Partial<DesktopSettings>;
    return {
      ...defaultSettings,
      ...parsed,
      risk: { ...defaultSettings.risk, ...(parsed.risk ?? {}) },
      research: { ...defaultSettings.research, ...(parsed.research ?? {}) },
    };
  },

  async saveSettings(settings: DesktopSettings): Promise<void> {
    if (isTauri) await invoke("save_desktop_settings", { settings });
    else localStorage.setItem("berkshire-nexus-settings", JSON.stringify(settings));
  },

  async promoteModel(): Promise<void> {
    if (isTauri) await invoke("promote_model");
    else await wait();
  },

  async keyStatus(): Promise<boolean> {
    if (isTauri) {
      const value = await invoke<{ configured: boolean }>("binance_key_status");
      return value.configured;
    }
    return false;
  },

  async saveKey(apiKey: string): Promise<void> {
    if (isTauri) await invoke("save_binance_key", { apiKey });
    else await wait();
  },

  async deleteKey(): Promise<void> {
    if (isTauri) await invoke("delete_binance_key");
    else await wait();
  },

  async preflight(tickers: string[]): Promise<Record<string, unknown>> {
    if (isTauri) return invoke<Record<string, unknown>>("binance_preflight", { tickers });
    await wait(700);
    throw new Error("浏览器预览无法访问系统钥匙串；请在 Tauri 桌面 App 中运行连接检查。");
  },

  async aiKeyStatus(): Promise<boolean> {
    if (isTauri) {
      const value = await invoke<{ configured: boolean }>("ai_key_status");
      return value.configured;
    }
    return false;
  },

  async secretStatus(): Promise<boolean> {
    if (isTauri) {
      const value = await invoke<{ configured: boolean }>("binance_secret_status");
      return value.configured;
    }
    return false;
  },

  async saveSecret(apiSecret: string): Promise<void> {
    if (isTauri) await invoke("save_binance_secret", { apiSecret });
    else await wait();
  },

  async deleteSecret(): Promise<void> {
    if (isTauri) await invoke("delete_binance_secret");
    else await wait();
  },

  async verifyCredentials(): Promise<CredentialCheck> {
    if (isTauri) return invoke<CredentialCheck>("verify_binance_credentials");
    await wait(600);
    throw new Error("浏览器预览无法访问系统钥匙串；请在 Tauri 桌面 App 中自检。");
  },

  async dailyBriefing(
    settings: DesktopSettings,
    options?: { perSegment?: number; segments?: string[]; minimumScore?: number },
  ): Promise<DailyBriefing> {
    if (isTauri) {
      return invoke<DailyBriefing>("daily_briefing", {
        researchConfig: settings.research,
        perSegment: options?.perSegment ?? 3,
        segments: options?.segments ?? null,
        minimumScore: options?.minimumScore ?? 60,
      });
    }
    await wait(900);
    throw new Error("浏览器预览无法访问系统钥匙串；请在 Tauri 桌面 App 中生成日报。");
  },

  async screenMarket(perSegment = 6): Promise<ScreenResult> {
    if (isTauri) return invoke<ScreenResult>("screen_market", { perSegment });
    await wait(700);
    throw new Error("浏览器预览无法选股；请在 Tauri 桌面 App 中运行。");
  },

  async sectorOverview(): Promise<SectorOverview> {
    if (isTauri) return invoke<SectorOverview>("sector_overview");
    await wait(400);
    throw new Error("浏览器预览无法读取全市场板块；请在 Tauri 桌面 App 中运行。");
  },

  async sectorConstituents(
    sector: string,
    options?: { limit?: number; order?: string },
  ): Promise<SectorConstituents> {
    if (isTauri) {
      return invoke<SectorConstituents>("sector_constituents", {
        sector,
        limit: options?.limit ?? 12,
        order: options?.order ?? "dollar_volume",
      });
    }
    await wait(300);
    throw new Error("浏览器预览无法读取板块成分；请在 Tauri 桌面 App 中运行。");
  },

  async searchTickers(query: string, limit = 20): Promise<TickerSearchResult> {
    if (isTauri) return invoke<TickerSearchResult>("search_tickers", { query, limit });
    await wait(200);
    throw new Error("浏览器预览无法搜索标的；请在 Tauri 桌面 App 中运行。");
  },

  async analyzeSelection(
    tickers: string[],
    settings: DesktopSettings,
    options?: { minimumScore?: number; label?: string },
  ): Promise<DailyBriefing> {
    if (isTauri) {
      return invoke<DailyBriefing>("analyze_selection", {
        tickers,
        researchConfig: settings.research,
        minimumScore: options?.minimumScore ?? 60,
        label: options?.label ?? "",
      });
    }
    await wait(700);
    throw new Error("浏览器预览无法运行分析；请在 Tauri 桌面 App 中运行。");
  },

  async liveAccount(): Promise<LiveAccount> {
    if (isTauri) return invoke<LiveAccount>("live_account");
    await wait(600);
    throw new Error("浏览器预览无法访问系统钥匙串；请在 Tauri 桌面 App 中查看真实账户。");
  },

  async liveReconcile(): Promise<LiveReconciliation> {
    if (isTauri) return invoke<LiveReconciliation>("live_reconcile");
    await wait(600);
    throw new Error("浏览器预览无法对账；请在 Tauri 桌面 App 中运行。");
  },

  async liveAcceptDisclaimer(): Promise<Record<string, unknown>> {
    if (isTauri) return invoke<Record<string, unknown>>("live_accept_disclaimer");
    await wait(600);
    throw new Error("浏览器预览无法签署免责声明；请在 Tauri 桌面 App 中运行。");
  },

  async liveCancelAll(symbol?: string): Promise<Record<string, unknown>> {
    if (isTauri) return invoke<Record<string, unknown>>("live_cancel_all", { symbol });
    await wait(600);
    throw new Error("浏览器预览无法撤单；请在 Tauri 桌面 App 中运行。");
  },

  /**
   * Redeem Simple Earn savings into CARD so a BUY can be funded.
   * Binance never auto-redeems, so this is the only way an Earn balance
   * becomes spendable. Gated by the same phrase as a live cycle.
   */
  async liveRedeemEarn(options: {
    productId: string;
    amount?: number;
    redeemAll: boolean;
    confirmation: string;
  }): Promise<Record<string, unknown>> {
    if (isTauri) {
      return invoke<Record<string, unknown>>("live_redeem_earn", {
        productId: options.productId,
        amount: options.amount,
        redeemAll: options.redeemAll,
        confirmation: options.confirmation,
      });
    }
    await wait(600);
    throw new Error("浏览器预览无法赎回理财；请在 Tauri 桌面 App 中运行。");
  },

  /**
   * Preview (submit=false) or place real orders (submit=true).
   * The confirmation phrase is validated in Rust and again in Python.
   */
  async runLiveCycle(
    settings: DesktopSettings,
    options: { confirmation: string; submit: boolean },
  ): Promise<LiveCycleResult> {
    if (isTauri) {
      return invoke<LiveCycleResult>("run_live_cycle", {
        tickers: settings.universe,
        riskConfig: settings.risk,
        researchConfig: settings.research,
        confirmation: options.confirmation,
        submit: options.submit,
      });
    }
    await wait(900);
    throw new Error("浏览器预览无法执行实盘链路；请在 Tauri 桌面 App 中运行。");
  },

  async saveAIKey(apiKey: string): Promise<void> {
    if (isTauri) await invoke("save_ai_key", { apiKey });
    else await wait();
  },

  async deleteAIKey(): Promise<void> {
    if (isTauri) await invoke("delete_ai_key");
    else await wait();
  },

  async testAIProvider(settings: DesktopSettings): Promise<AnalysisReport["ai_research"]> {
    if (isTauri) {
      return invoke<AnalysisReport["ai_research"]>("test_ai_provider", {
        researchConfig: settings.research,
      });
    }
    await wait(600);
    return {
      status: "ok",
      provider: settings.research.ai_provider,
      model: settings.research.ai_model,
      prompt_version: "research-synthesis-v1",
      generated_at_utc: new Date().toISOString(),
      latency_ms: 600,
      summary: "浏览器演示连接成功。",
      thesis: "",
      catalysts: [],
      risks: [],
      action_bias: "INSUFFICIENT_EVIDENCE",
      confidence: 0,
      citations: [],
      usage: {},
      error: null,
    };
  },
};
