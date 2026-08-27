import { invoke } from "@tauri-apps/api/core";
import { defaultSettings, mockReports, mockSnapshot } from "./mock";
import type {
  AgentRuntimeStatus,
  AnalysisReport,
  AppSnapshot,
  DesktopSettings,
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
