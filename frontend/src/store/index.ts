import { create } from "zustand";
import { devtools } from "zustand/middleware";
import type {
  Alert,
  ArbitrageOpportunity,
  ExchangeStatus,
  ExecutionPlan,
  Orderbook,
  RiskRule,
  SpreadInfo,
  StrategyConfig,
  SystemHealth,
  SystemMetrics,
  Ticker,
  TimeInterval,
  TradingMode,
  WsChannel,
  WsStatus,
} from "@/types";

// ============================================================
// System Store
// ============================================================

interface SystemState {
  health: SystemHealth | null;
  metrics: SystemMetrics | null;
  exchanges: ExchangeStatus[];
  wsStatus: WsStatus | null;
  wsChannelStatus: Record<string, boolean>;
  scannerStatus: "idle" | "scanning" | "paused" | "error";
  setHealth: (health: SystemHealth) => void;
  setMetrics: (metrics: SystemMetrics) => void;
  setExchanges: (exchanges: ExchangeStatus[]) => void;
  setWsStatus: (wsStatus: WsStatus) => void;
  updateWsStatus: (channel: WsChannel, connected: boolean) => void;
  setScannerStatus: (status: "idle" | "scanning" | "paused" | "error") => void;
}

export const useSystemStore = create<SystemState>()(
  devtools(
    (set) => ({
      health: null,
      metrics: null,
      exchanges: [],
      wsStatus: null,
      wsChannelStatus: {},
      scannerStatus: "idle",
      setHealth: (health) => set({ health }, false, "setHealth"),
      setMetrics: (metrics) => set({ metrics }, false, "setMetrics"),
      setExchanges: (exchanges) => set({ exchanges }, false, "setExchanges"),
      setWsStatus: (wsStatus) => set({ wsStatus }, false, "setWsStatus"),
      updateWsStatus: (channel, connected) =>
        set(
          (state) => ({
            wsChannelStatus: { ...state.wsChannelStatus, [channel]: connected },
          }),
          false,
          "updateWsStatus"
        ),
      setScannerStatus: (scannerStatus) =>
        set({ scannerStatus }, false, "setScannerStatus"),
    }),
    { name: "system-store" }
  )
);

// ============================================================
// Market Store
// ============================================================

interface MarketState {
  tickers: Map<string, Ticker>;
  orderbooks: Map<string, Orderbook>;
  spreads: SpreadInfo[];
  opportunities: ArbitrageOpportunity[];
  setTicker: (key: string, ticker: Ticker) => void;
  setTickers: (tickers: Ticker[]) => void;
  setOrderbook: (key: string, orderbook: Orderbook) => void;
  setSpreads: (spreads: SpreadInfo[]) => void;
  setOpportunities: (opportunities: ArbitrageOpportunity[]) => void;
  addOpportunity: (opportunity: ArbitrageOpportunity) => void;
  removeExpiredOpportunities: () => void;
}

export const useMarketStore = create<MarketState>()(
  devtools(
    (set, get) => ({
      tickers: new Map(),
      orderbooks: new Map(),
      spreads: [],
      opportunities: [],

      setTicker: (key, ticker) =>
        set(
          (state) => {
            const next = new Map(state.tickers);
            next.set(key, ticker);
            return { tickers: next };
          },
          false,
          "setTicker"
        ),

      setTickers: (tickers) =>
        set(
          () => {
            const map = new Map<string, Ticker>();
            for (const t of tickers) {
              map.set(`${t.exchange}:${t.symbol}`, t);
            }
            return { tickers: map };
          },
          false,
          "setTickers"
        ),

      setOrderbook: (key, orderbook) =>
        set(
          (state) => {
            const next = new Map(state.orderbooks);
            next.set(key, orderbook);
            return { orderbooks: next };
          },
          false,
          "setOrderbook"
        ),

      setSpreads: (spreads) => set({ spreads }, false, "setSpreads"),

      setOpportunities: (opportunities) =>
        set({ opportunities }, false, "setOpportunities"),

      addOpportunity: (opportunity) =>
        set(
          (state) => ({
            opportunities: [
              opportunity,
              ...state.opportunities.filter((o) => o.id !== opportunity.id),
            ].slice(0, 100),
          }),
          false,
          "addOpportunity"
        ),

      removeExpiredOpportunities: () => {
        const now = new Date().toISOString();
        const current = get().opportunities;
        const filtered = current.filter((o) => o.expiresAt > now);
        if (filtered.length !== current.length) {
          set({ opportunities: filtered }, false, "removeExpired");
        }
      },
    }),
    { name: "market-store" }
  )
);

// ============================================================
// Execution Store
// ============================================================

interface ExecutionState {
  executions: ExecutionPlan[];
  activeExecutions: ExecutionPlan[];
  setExecutions: (executions: ExecutionPlan[]) => void;
  setActiveExecutions: (executions: ExecutionPlan[]) => void;
  updateExecution: (execution: ExecutionPlan) => void;
  addExecution: (execution: ExecutionPlan) => void;
}

export const useExecutionStore = create<ExecutionState>()(
  devtools(
    (set) => ({
      executions: [],
      activeExecutions: [],

      setExecutions: (executions) =>
        set({ executions }, false, "setExecutions"),

      setActiveExecutions: (activeExecutions) =>
        set({ activeExecutions }, false, "setActiveExecutions"),

      updateExecution: (execution) =>
        set(
          (state) => ({
            executions: state.executions.map((e) =>
              e.id === execution.id ? execution : e
            ),
            activeExecutions: execution.status === "executing" || execution.status === "pending"
              ? state.activeExecutions.map((e) =>
                  e.id === execution.id ? execution : e
                )
              : state.activeExecutions.filter((e) => e.id !== execution.id),
          }),
          false,
          "updateExecution"
        ),

      addExecution: (execution) =>
        set(
          (state) => ({
            executions: [execution, ...state.executions].slice(0, 200),
            activeExecutions:
              execution.status === "executing" || execution.status === "pending"
                ? [execution, ...state.activeExecutions]
                : state.activeExecutions,
          }),
          false,
          "addExecution"
        ),
    }),
    { name: "execution-store" }
  )
);

// ============================================================
// Alert Store
// ============================================================

interface AlertState {
  alerts: Alert[];
  activeAlerts: Alert[];
  unreadCount: number;
  setAlerts: (alerts: Alert[]) => void;
  setActiveAlerts: (alerts: Alert[]) => void;
  addAlert: (alert: Alert) => void;
  markRead: (id: string) => void;
  resolveAlert: (id: string) => void;
  setUnreadCount: (count: number) => void;
}

export const useAlertStore = create<AlertState>()(
  devtools(
    (set) => ({
      alerts: [],
      activeAlerts: [],
      unreadCount: 0,

      setAlerts: (alerts) =>
        set(
          {
            alerts,
            unreadCount: alerts.filter((a) => !a.read).length,
          },
          false,
          "setAlerts"
        ),

      setActiveAlerts: (activeAlerts) =>
        set({ activeAlerts }, false, "setActiveAlerts"),

      addAlert: (alert) =>
        set(
          (state) => ({
            alerts: [alert, ...state.alerts].slice(0, 500),
            activeAlerts: !alert.resolved
              ? [alert, ...state.activeAlerts]
              : state.activeAlerts,
            unreadCount: alert.read
              ? state.unreadCount
              : state.unreadCount + 1,
          }),
          false,
          "addAlert"
        ),

      markRead: (id) =>
        set(
          (state) => ({
            alerts: state.alerts.map((a) =>
              a.id === id ? { ...a, read: true } : a
            ),
            unreadCount: Math.max(0, state.unreadCount - 1),
          }),
          false,
          "markRead"
        ),

      resolveAlert: (id) =>
        set(
          (state) => ({
            alerts: state.alerts.map((a) =>
              a.id === id
                ? { ...a, resolved: true, resolvedAt: new Date().toISOString() }
                : a
            ),
            activeAlerts: state.activeAlerts.filter((a) => a.id !== id),
          }),
          false,
          "resolveAlert"
        ),

      setUnreadCount: (count) =>
        set({ unreadCount: count }, false, "setUnreadCount"),
    }),
    { name: "alert-store" }
  )
);

// ============================================================
// Settings Store
// ============================================================

interface SettingsState {
  strategies: StrategyConfig[];
  riskRules: RiskRule[];
  tradingMode: TradingMode;
  setStrategies: (strategies: StrategyConfig[]) => void;
  updateStrategy: (strategy: StrategyConfig) => void;
  setRiskRules: (rules: RiskRule[]) => void;
  updateRiskRule: (rule: RiskRule) => void;
  setTradingMode: (mode: TradingMode) => void;
}

export const useSettingsStore = create<SettingsState>()(
  devtools(
    (set) => ({
      strategies: [],
      riskRules: [],
      tradingMode: "paper",

      setStrategies: (strategies) =>
        set({ strategies }, false, "setStrategies"),

      updateStrategy: (strategy) =>
        set(
          (state) => ({
            strategies: state.strategies.map((s) =>
              s.id === strategy.id ? strategy : s
            ),
          }),
          false,
          "updateStrategy"
        ),

      setRiskRules: (riskRules) =>
        set({ riskRules }, false, "setRiskRules"),

      updateRiskRule: (rule) =>
        set(
          (state) => ({
            riskRules: state.riskRules.map((r) =>
              r.id === rule.id ? rule : r
            ),
          }),
          false,
          "updateRiskRule"
        ),

      setTradingMode: (tradingMode) =>
        set({ tradingMode }, false, "setTradingMode"),
    }),
    { name: "settings-store" }
  )
);

// ============================================================
// Selection Store
// ============================================================

interface SelectionState {
  selectedOpportunity: ArbitrageOpportunity | null;
  selectedExecution: ExecutionPlan | null;
  setSelectedOpportunity: (opportunity: ArbitrageOpportunity | null) => void;
  setSelectedExecution: (execution: ExecutionPlan | null) => void;
}

export const useSelectionStore = create<SelectionState>()(
  devtools(
    (set) => ({
      selectedOpportunity: null,
      selectedExecution: null,
      setSelectedOpportunity: (selectedOpportunity) =>
        set({ selectedOpportunity }, false, "setSelectedOpportunity"),
      setSelectedExecution: (selectedExecution) =>
        set({ selectedExecution }, false, "setSelectedExecution"),
    }),
    { name: "selection-store" }
  )
);

// ============================================================
// UI Store
// ============================================================

interface UIState {
  sidebarCollapsed: boolean;
  timeRange: TimeInterval;
  toggleSidebar: () => void;
  setTimeRange: (range: TimeInterval) => void;
}

export const useUIStore = create<UIState>()(
  devtools(
    (set) => ({
      sidebarCollapsed: false,
      timeRange: "1h",
      toggleSidebar: () =>
        set(
          (state) => ({ sidebarCollapsed: !state.sidebarCollapsed }),
          false,
          "toggleSidebar"
        ),
      setTimeRange: (timeRange) =>
        set({ timeRange }, false, "setTimeRange"),
    }),
    { name: "ui-store" }
  )
);
