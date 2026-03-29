import type {
  Alert,
  AlertFilterParams,
  AnalyticsDashboard,
  AnalyticsParams,
  ApiError,
  ArbitrageOpportunity,
  AuditEntry,
  AuditStats,
  Balance,
  ExchangeAllocation,
  ExchangeId,
  ExchangeStatus,
  ExecutionDetail,
  ExecutionFilterParams,
  ExecutionPlan,
  ExposureData,
  FailureAnalysis,
  InventoryFullSummary,
  InventorySummary,
  OpportunityFilter,
  Order,
  OrderFilterParams,
  Orderbook,
  PaginatedResponse,
  PnlSummary,
  ProfitByExchange,
  ProfitByPeriod,
  ProfitByStrategy,
  ProfitBySymbol,
  RebalanceSuggestion,
  RiskDecision,
  RiskEvent,
  RiskExposure,
  RiskRule,
  ScannerStatus,
  SlippageAnalysis,
  SpreadInfo,
  StrategyConfig,
  SystemHealth,
  SystemMetrics,
  Ticker,
  WsStatus,
} from "@/types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ============================================================
// Error class
// ============================================================

export class ApiRequestError extends Error implements ApiError {
  status: number;
  detail?: string;
  code?: string;

  constructor(status: number, message: string, detail?: string, code?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

// ============================================================
// Core request helpers
// ============================================================

function buildQueryString(params?: Record<string, unknown>): string {
  if (!params) return "";
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null
  );
  if (entries.length === 0) return "";
  const qs = new URLSearchParams();
  for (const [key, value] of entries) {
    qs.set(key, String(value));
  }
  return `?${qs.toString()}`;
}

async function request<T>(
  path: string,
  options?: RequestInit & { params?: Record<string, unknown> }
): Promise<T> {
  const { params, ...init } = options ?? {};
  const url = `${BASE_URL}${path}${buildQueryString(params)}`;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };

  const res = await fetch(url, { ...init, headers });

  if (!res.ok) {
    let detail: string | undefined;
    let code: string | undefined;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message;
      code = body.code;
    } catch {
      // ignore parse failure
    }
    throw new ApiRequestError(
      res.status,
      detail ?? res.statusText,
      detail,
      code
    );
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

function get<T>(path: string, options?: { params?: Record<string, unknown> }): Promise<T> {
  return request<T>(path, { method: "GET", ...options });
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}

// ============================================================
// Mock fallback helper
// ============================================================

export async function withMockFallback<T>(apiCall: () => Promise<T>, mockData: T): Promise<T> {
  try {
    return await apiCall();
  } catch (err) {
    if (process.env.NODE_ENV === 'development') {
      console.warn('[API] Backend unreachable — returning mock data. Start the backend on', BASE_URL, err);
    }
    return mockData;
  }
}

// ============================================================
// System API
// ============================================================

/** Normalize backend exchange data to ExchangeStatus */
function normalizeExchangeStatus(raw: Record<string, any>): ExchangeStatus {
  const apiStatus = String(raw.api_status ?? raw.apiStatus ?? "").toUpperCase();
  const isConnected = apiStatus === "CONNECTED" || raw.connected === true || raw.is_active === true;
  const statusStr = isConnected ? "healthy" : apiStatus === "DEGRADED" ? "degraded" : "down";
  return {
    exchange: (raw.name ?? raw.exchange ?? "") as ExchangeId,
    name: raw.display_name ?? raw.name ?? raw.exchange ?? "",
    connected: isConnected,
    latencyMs: raw.latency_ms ?? raw.latencyMs ?? 0,
    rateLimitRemaining: raw.rate_limit_remaining ?? raw.rateLimitRemaining ?? 0,
    rateLimitTotal: raw.rate_limit_total ?? raw.rateLimitTotal ?? 0,
    lastHeartbeat: raw.last_heartbeat ?? raw.lastHeartbeat ?? new Date().toISOString(),
    status: statusStr as "healthy" | "degraded" | "down",
    features: raw.features ?? [],
  };
}

export const systemApi = {
  getHealth: () => request<SystemHealth>("/api/system/health"),

  getMetrics: () => request<SystemMetrics>("/api/system/metrics"),

  getExchanges: async () => {
    const raw = await request<any>("/api/system/exchanges");
    if (!Array.isArray(raw)) return [];
    return raw.map(normalizeExchangeStatus);
  },

  getWsStatus: () => request<WsStatus>("/api/system/ws-status"),
};

// ============================================================
// Market API
// ============================================================

/** Normalize backend snake_case ticker to frontend camelCase Ticker type. */
/** Convert scanner snake_case opportunity to frontend ArbitrageOpportunity */
function normalizeExecutionResult(raw: Record<string, any>): ExecutionPlan {
  const n = (v: any) => Number(v) || 0;
  const stateToStatus: Record<string, string> = {
    COMPLETED: "completed",
    FILLED: "completed",
    FAILED: "failed",
    RISK_REJECTED: "failed",
    HEDGING: "partial",
    PARTIALLY_FILLED: "partial",
    EXECUTING: "executing",
    READY: "pending",
    PENDING: "pending",
    SUBMITTING: "pending",
  };
  const state = raw.state ?? "COMPLETED";
  const legs = (raw.legs_detail ?? []).map((l: any, i: number) => ({
    id: l.order_id ?? `leg-${i}`,
    exchange: l.exchange ?? "",
    symbol: l.symbol ?? raw.symbol ?? "",
    side: (l.side ?? "BUY").toLowerCase(),
    price: n(l.actual_price ?? l.planned_price),
    quantity: n(l.actual_quantity ?? l.planned_quantity),
    filled: n(l.actual_quantity ?? l.planned_quantity),
    cost: n(l.actual_price ?? l.planned_price) * n(l.actual_quantity ?? l.planned_quantity),
    fee: n(l.fee),
    status: l.status === "FILLED" ? "filled" : l.status === "FAILED" ? "rejected" : "open",
    orderId: l.exchange_order_id ?? "",
    executedAt: l.filled_at ? new Date(l.filled_at * 1000).toISOString() : new Date().toISOString(),
    latencyMs: n(l.latency_ms),
  }));
  // If no detailed legs but we know there are 2 legs (cross-exchange)
  const legCount = n(raw.legs);
  if (legs.length === 0 && legCount > 0) {
    for (let i = 0; i < legCount; i++) {
      legs.push({
        id: `leg-${i}`,
        exchange: i === 0 ? (raw.buy_exchange ?? "") : (raw.sell_exchange ?? ""),
        symbol: raw.symbol ?? "",
        side: i === 0 ? "buy" : "sell",
        price: 0,
        quantity: 0,
        filled: 0,
        cost: 0,
        fee: n(raw.total_fees_usdt) / legCount,
        status: state === "COMPLETED" || state === "FILLED" ? "filled" : "open",
        orderId: "",
        executedAt: new Date().toISOString(),
        latencyMs: 0,
      });
    }
  }
  const startedAt = raw.started_at ? new Date(n(raw.started_at) * 1000).toISOString() : new Date().toISOString();
  const completedAt = raw.completed_at ? new Date(n(raw.completed_at) * 1000).toISOString() : new Date().toISOString();
  return {
    id: raw.execution_id ?? "",
    opportunityId: raw.opportunity_id ?? "",
    strategyId: "",
    strategyType: normalizeStrategyType(raw.strategy_type ?? "cross_exchange"),
    symbol: raw.symbol ?? "",
    status: (stateToStatus[state] ?? "completed") as any,
    legs,
    expectedProfit: n(raw.planned_profit_pct) * n(raw.total_notional ?? 100) / 100,
    actualProfit: n(raw.actual_profit_usdt),
    expectedProfitPercent: n(raw.planned_profit_pct),
    actualProfitPercent: n(raw.actual_profit_pct),
    slippage: n(raw.total_slippage_usdt),
    totalFees: n(raw.total_fees_usdt),
    totalVolume: n(raw.total_notional ?? 0),
    startedAt,
    completedAt,
    duration: n(raw.execution_time_ms),
    error: raw.error_message || null,
  };
}

/** Map backend strategy_type strings to the frontend StrategyType union. */
function normalizeStrategyType(raw: string): ArbitrageOpportunity["type"] {
  const map: Record<string, ArbitrageOpportunity["type"]> = {
    cross_exchange: "cross_exchange",
    CROSS_EXCHANGE: "cross_exchange",
    spatial: "cross_exchange",
    triangular: "triangular",
    TRIANGULAR: "triangular",
    futures_spot: "funding_rate",
    FUTURES_SPOT: "funding_rate",
    funding_rate: "funding_rate",
    statistical: "statistical",
    STATISTICAL: "statistical",
  };
  return map[raw] ?? map[raw.toLowerCase()] ?? "cross_exchange";
}

function normalizeOpportunity(raw: Record<string, any>): ArbitrageOpportunity {
  const n = (v: any) => Number(v) || 0;
  const ts = (v: any) => {
    if (!v) return new Date().toISOString();
    if (typeof v === "number") return new Date(v * 1000).toISOString();
    return String(v);
  };
  return {
    id: raw.id ?? "",
    type: normalizeStrategyType(raw.strategy_type ?? raw.type ?? "cross_exchange"),
    symbol: raw.symbol ?? "",
    buyExchange: (raw.buy_exchange ?? raw.buyExchange ?? "") as ExchangeId,
    sellExchange: (raw.sell_exchange ?? raw.sellExchange ?? "") as ExchangeId,
    buyPrice: n(raw.buy_price ?? raw.buyPrice),
    sellPrice: n(raw.sell_price ?? raw.sellPrice),
    spreadPercent: n(raw.spread_pct ?? raw.spreadPercent),
    spreadAbsolute: n(raw.spread_absolute ?? raw.spreadAbsolute ?? (n(raw.sell_price ?? raw.sellPrice) - n(raw.buy_price ?? raw.buyPrice))),
    estimatedProfit: n(raw.estimated_profit ?? raw.estimatedProfit ?? raw.executable_value_usdt ?? 0),
    estimatedProfitPercent: n(raw.theoretical_profit_pct ?? raw.estimatedProfitPercent),
    maxVolume: n(raw.executable_quantity ?? raw.maxVolume ?? 0.001),
    fees: n(raw.buy_fee_pct ?? 0) + n(raw.sell_fee_pct ?? 0),
    netProfit: n(raw.estimated_net_profit_pct ?? raw.netProfit) * n(raw.executable_value_usdt ?? 1) / 100,
    netProfitPercent: n(raw.estimated_net_profit_pct ?? raw.netProfitPercent),
    confidence: n(raw.confidence_score ?? raw.confidence ?? 0.5),
    ttl: n(raw.ttl ?? 5),
    detectedAt: ts(raw.detected_at ?? raw.detectedAt),
    expiresAt: ts(raw.expires_at ?? raw.expiresAt),
  };
}

function normalizeTicker(raw: Record<string, unknown>): Ticker {
  return {
    symbol: (raw.symbol as string) ?? "",
    exchange: ((raw.exchange as string) ?? "") as ExchangeId,
    bid: (raw.bid as number) ?? 0,
    ask: (raw.ask as number) ?? 0,
    bidSize: (raw.bid_size ?? raw.bidSize ?? 0) as number,
    askSize: (raw.ask_size ?? raw.askSize ?? 0) as number,
    last: (raw.last_price ?? raw.last ?? 0) as number,
    volume24h: (raw.volume_24h ?? raw.volume24h ?? 0) as number,
    change24h: (raw.change_24h ?? raw.change24h ?? 0) as number,
    changePercent24h: (raw.change_percent_24h ?? raw.changePercent24h ?? 0) as number,
    high24h: (raw.high_24h ?? raw.high24h ?? 0) as number,
    low24h: (raw.low_24h ?? raw.low24h ?? 0) as number,
    timestamp: (raw.timestamp as string) ?? new Date().toISOString(),
  };
}

export const marketApi = {
  getTickers: async (params?: { symbol?: string; exchange?: string }) => {
    const raw = await request<any>("/api/market/tickers", { params });
    return (Array.isArray(raw) ? raw : []).map(normalizeTicker);
  },

  getTicker: async (exchange: string, symbol: string) => {
    const raw = await request<Record<string, unknown>>(`/api/market/tickers/${exchange}/${symbol}`);
    return normalizeTicker(raw);
  },

  getOrderbook: (exchange: string, symbol: string) =>
    request<Orderbook>(`/api/market/orderbook/${exchange}/${symbol}`),

  getSpreads: (params?: { symbol?: string }) =>
    request<SpreadInfo[]>("/api/market/spreads", { params }),

  getSpread: (symbol: string) =>
    request<SpreadInfo[]>(`/api/market/spreads/${symbol}`),

  getOpportunities: async (params?: OpportunityFilter) => {
    const res = await request<{ items?: any[]; opportunities?: any[] }>("/api/market/arbitrage-opportunities", {
      params: params as Record<string, unknown>,
    });
    const raw = res.items ?? res.opportunities ?? [];
    return raw.map(normalizeOpportunity);
  },
};

// ============================================================
// Strategy API
// ============================================================

export const strategyApi = {
  getStrategies: () =>
    request<StrategyConfig[]>("/api/strategies"),

  getStrategy: (id: string) =>
    request<StrategyConfig>(`/api/strategies/${id}`),

  updateStrategy: (id: string, data: Partial<StrategyConfig>) =>
    request<StrategyConfig>(`/api/strategies/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  enableStrategy: (id: string) =>
    request<StrategyConfig>(`/api/strategies/${id}/enable`, {
      method: "POST",
    }),

  disableStrategy: (id: string) =>
    request<StrategyConfig>(`/api/strategies/${id}/disable`, {
      method: "POST",
    }),
};

// ============================================================
// Execution API
// ============================================================

export const executionApi = {
  getExecutions: (params?: ExecutionFilterParams) =>
    request<PaginatedResponse<ExecutionPlan>>("/api/executions", {
      params: params as Record<string, unknown>,
    }),

  getExecution: (id: string) =>
    request<ExecutionPlan>(`/api/executions/${id}`),

  getActiveExecutions: () =>
    request<ExecutionPlan[]>("/api/executions/active"),

  triggerExecution: (opportunityId: string) =>
    request<ExecutionPlan>("/api/executions/trigger", {
      method: "POST",
      body: JSON.stringify({ opportunityId }),
    }),

  // Phase 3: Execution Coordinator endpoints
  executeOpportunity: (opportunityId: string, mode?: string) =>
    post<ExecutionDetail>('/api/executions/execute-opportunity', { opportunity_id: opportunityId, mode: mode || 'PAPER' }),

  executeCrossExchange: (data: { symbol: string; buy_exchange: string; sell_exchange: string; quantity: number; mode?: string }) =>
    post<ExecutionDetail>('/api/executions/cross-exchange', data),

  executeTriangular: (data: { exchange: string; path: string[]; start_amount: number; mode?: string }) =>
    post<ExecutionDetail>('/api/executions/triangular', data),

  getActiveExecutionDetail: () =>
    get<ExecutionDetail[]>('/api/executions/active-detail'),

  getExecutionDetail: (id: string) =>
    get<ExecutionDetail>(`/api/executions/${id}/detail`),

  getHistory: async (limit: number = 50): Promise<ExecutionPlan[]> => {
    const raw = await get<any>(`/api/executions/history?limit=${limit}`);
    if (!Array.isArray(raw)) return [];
    return raw.map(normalizeExecutionResult);
  },
};

// ============================================================
// Order API
// ============================================================

export const orderApi = {
  getOrders: (params?: OrderFilterParams) =>
    request<PaginatedResponse<Order>>("/api/orders", {
      params: params as Record<string, unknown>,
    }),

  getOrder: (id: string) => request<Order>(`/api/orders/${id}`),
};

// ============================================================
// Risk API
// ============================================================

/** Map backend category to a default action for display purposes. */
const CATEGORY_ACTION_MAP: Record<string, RiskRule["action"]> = {
  exposure: "block",
  loss: "halt",
  execution: "warn",
  spread: "warn",
};

/** Normalize a backend risk-rule object (snake_case, flat) into the frontend RiskRule shape. */
function normalizeRiskRule(raw: Record<string, unknown>, index: number): RiskRule {
  return {
    id: (raw.id as string) ?? (raw.name as string) ?? `rule-${index}`,
    type: (raw.type ?? raw.category ?? "max_position_size") as RiskRule["type"],
    name: (raw.name as string) ?? "",
    description: (raw.description as string) ?? "",
    enabled: (raw.enabled as boolean) ?? true,
    threshold: Number(raw.threshold ?? 0),
    currentValue: Number(raw.current_value ?? raw.currentValue ?? 0),
    unit: (raw.unit as string) ?? "",
    action: (raw.action as RiskRule["action"]) ?? CATEGORY_ACTION_MAP[raw.category as string] ?? "warn",
    cooldownSeconds: Number(raw.cooldown_seconds ?? raw.cooldownSeconds ?? 0),
    lastTriggered: (raw.last_triggered ?? raw.lastTriggered ?? null) as string | null,
    updatedAt: (raw.updated_at ?? raw.updatedAt ?? new Date().toISOString()) as string,
  };
}

/** Normalize a backend risk-event object into the frontend RiskEvent shape. */
function normalizeRiskEvent(raw: Record<string, unknown>, index: number): RiskEvent {
  return {
    id: (raw.id as string) ?? `event-${index}`,
    ruleId: (raw.rule_id ?? raw.ruleId ?? "") as string,
    ruleName: (raw.rule_name ?? raw.ruleName ?? "") as string,
    ruleType: (raw.rule_type ?? raw.ruleType ?? "max_position_size") as RiskRule["type"],
    severity: (raw.severity ?? "low") as RiskEvent["severity"],
    message: (raw.message as string) ?? "",
    details: (raw.details as Record<string, unknown>) ?? {},
    triggered: (raw.triggered as boolean) ?? false,
    action: (raw.action as string) ?? "monitor",
    timestamp: (raw.timestamp as string) ?? new Date().toISOString(),
  };
}

/**
 * Normalize backend exposure data.
 * The backend may return an array of per-asset rows instead of
 * the aggregated RiskExposure object the frontend expects.
 */
function normalizeExposure(raw: unknown): RiskExposure {
  // If the backend already returns the expected shape, pass through.
  if (raw && typeof raw === "object" && !Array.isArray(raw) && "totalExposureUsd" in raw) {
    return raw as RiskExposure;
  }

  // Backend returns an array: [{exchange, asset, amount, usd_value, pct_of_total}, ...]
  const rows = Array.isArray(raw) ? raw : [];
  const byExchange: Record<string, number> = {};
  const bySymbol: Record<string, number> = {};
  let total = 0;

  for (const row of rows) {
    const exchange = (row.exchange ?? "") as string;
    const asset = (row.asset ?? "") as string;
    const usdValue = Number(row.usd_value ?? row.usdValue ?? 0);

    total += usdValue;
    byExchange[exchange] = (byExchange[exchange] ?? 0) + usdValue;
    bySymbol[asset] = (bySymbol[asset] ?? 0) + usdValue;
  }

  return {
    totalExposureUsd: total,
    maxExposureUsd: 200000, // sensible default when backend doesn't provide it
    utilizationPercent: total > 0 ? Math.round((total / 200000) * 1000) / 10 : 0,
    byExchange: byExchange as Record<ExchangeId, number>,
    bySymbol,
    openPositions: rows.length,
    pendingOrders: 0,
    timestamp: new Date().toISOString(),
  };
}

export const riskApi = {
  getRiskRules: async (): Promise<RiskRule[]> => {
    const raw = await request<any>("/api/risk/rules");
    return (Array.isArray(raw) ? raw : []).map(normalizeRiskRule);
  },

  updateRiskRule: (id: string, data: Partial<RiskRule>) =>
    request<RiskRule>(`/api/risk/rules/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getRiskEvents: async (params?: { severity?: string; limit?: number }): Promise<RiskEvent[]> => {
    const raw = await request<any>("/api/risk/events", { params });
    return (Array.isArray(raw) ? raw : []).map(normalizeRiskEvent);
  },

  getExposure: async (): Promise<RiskExposure> => {
    const raw = await request<unknown>("/api/risk/exposure");
    return normalizeExposure(raw);
  },

  // Phase 3: Risk check
  checkRisk: (data: { symbol: string; buy_exchange: string; sell_exchange: string; buy_price: number; sell_price: number; quantity: number; estimated_profit_pct: number }) =>
    post<RiskDecision>('/api/risk/check', data),
};

// ============================================================
// Inventory API
// ============================================================

// ---------------------------------------------------------------------------
// Inventory normalizers (backend snake_case → frontend camelCase)
// ---------------------------------------------------------------------------

function normalizeBalance(raw: Record<string, unknown>): Balance {
  return {
    asset: (raw.asset as string) ?? "",
    exchange: (raw.exchange_name ?? raw.exchange ?? "") as ExchangeId,
    free: Number(raw.free ?? 0),
    locked: Number(raw.locked ?? 0),
    total: Number(raw.total ?? 0),
    usdValue: Number(raw.usd_value ?? raw.usdValue ?? 0),
    updatedAt: (raw.updated_at ?? raw.updatedAt ?? "") as string,
  };
}

function normalizeExchangeAllocation(raw: Record<string, unknown>): ExchangeAllocation {
  const balances = Array.isArray(raw.balances) ? raw.balances : (Array.isArray(raw.assets) ? raw.assets : []);
  return {
    exchange: (raw.exchange as string ?? "") as ExchangeId,
    totalUsd: Number(raw.total_usd_value ?? raw.totalUsd ?? 0),
    percentOfTotal: Number(raw.pct_of_portfolio ?? raw.percentOfTotal ?? 0),
    assets: balances.map((b: Record<string, unknown>) => normalizeBalance(b)),
    status: (raw.status as ExchangeAllocation["status"]) ?? "connected",
  };
}

function normalizeInventorySummary(raw: Record<string, unknown>): InventorySummary {
  const allocations = Array.isArray(raw.allocations) ? raw.allocations : [];
  const exchanges = allocations.map((a: Record<string, unknown>) => normalizeExchangeAllocation(a));
  return {
    totalValueUsd: Number(raw.total_usd_value ?? raw.totalValueUsd ?? 0),
    change24h: Number(raw.change_24h ?? raw.change24h ?? 0),
    changePercent24h: Number(raw.change_percent_24h ?? raw.changePercent24h ?? 0),
    exchanges,
    topAssets: Array.isArray(raw.assets)
      ? raw.assets.map((a: Record<string, unknown>) => ({
          asset: (a.asset as string) ?? "",
          totalUsd: Number(a.total_usd_value ?? 0),
          percent: Number(a.pct ?? 0),
        }))
      : [],
  };
}

function normalizeRebalanceSuggestion(raw: Record<string, unknown>): RebalanceSuggestion {
  return {
    id: String(raw.id ?? ""),
    fromExchange: (raw.from_exchange ?? raw.fromExchange ?? "") as ExchangeId,
    toExchange: (raw.to_exchange ?? raw.toExchange ?? "") as ExchangeId,
    asset: (raw.asset as string) ?? "",
    amount: Number(raw.suggested_quantity ?? raw.amount ?? 0),
    usdValue: Number(raw.usd_value ?? raw.usdValue ?? 0),
    reason: (raw.reason as string) ?? "",
    priority: (raw.priority as RebalanceSuggestion["priority"]) ?? "low",
    estimatedCost: Number(raw.estimated_cost ?? raw.estimatedCost ?? 0),
    estimatedTime: (raw.estimated_time ?? raw.estimatedTime ?? "") as string,
  };
}

function normalizeInventoryFullSummary(raw: Record<string, unknown>): InventoryFullSummary {
  const allocations = Array.isArray(raw.allocations) ? raw.allocations : [];
  return {
    total_value_usdt: Number(raw.total_value_usdt ?? 0),
    exchange_count: Number(raw.exchange_count ?? 0),
    asset_count: Number(raw.asset_count ?? 0),
    last_refresh_at: Number(raw.last_refresh_at ?? 0),
    stablecoin_balance: Number(raw.stablecoin_balance ?? 0),
    allocations: allocations.map((a: Record<string, unknown>) => normalizeExchangeAllocation(a)),
  };
}

export const inventoryApi = {
  getBalances: async (params?: { exchange?: string; asset?: string }) => {
    const raw = await request<Record<string, unknown>[]>("/api/inventory/balances", { params });
    return (Array.isArray(raw) ? raw : []).map(normalizeBalance);
  },

  getExchangeBalances: async (exchange: string) => {
    const raw = await request<Record<string, unknown>>(`/api/inventory/balances/${exchange}`);
    return normalizeExchangeAllocation(raw);
  },

  getAllocation: async () => {
    const raw = await request<Record<string, unknown>>("/api/inventory/allocation");
    return normalizeInventorySummary(raw);
  },

  getRebalanceSuggestions: async () => {
    const raw = await request<Record<string, unknown>[]>("/api/inventory/rebalance-suggestions");
    return (Array.isArray(raw) ? raw : []).map(normalizeRebalanceSuggestion);
  },

  // Phase 3: Enhanced inventory endpoints
  getExposure: () =>
    get<ExposureData>('/api/inventory/exposure'),

  getSummary: async () => {
    const raw = await get<Record<string, unknown>>('/api/inventory/summary');
    return normalizeInventoryFullSummary(raw);
  },
};

// ============================================================
// Analytics API — normalizers (backend snake_case → frontend camelCase)
// ============================================================

/** Safely coerce a value to number (handles string numerics from the backend). */
function toNum(v: unknown): number {
  if (typeof v === "number") return v;
  if (typeof v === "string") { const n = Number(v); return Number.isNaN(n) ? 0 : n; }
  return 0;
}

function normalizePnlSummary(raw: Record<string, unknown>): PnlSummary {
  return {
    totalPnl: toNum(raw.total_net_profit_usdt ?? raw.totalPnl),
    totalPnlPercent: toNum(raw.total_pnl_percent ?? raw.totalPnlPercent ?? 0),
    totalTrades: toNum(raw.trade_count ?? raw.totalTrades),
    winningTrades: toNum(raw.win_count ?? raw.winningTrades ?? 0),
    losingTrades: toNum(raw.loss_count ?? raw.losingTrades ?? 0),
    winRate: toNum(raw.win_rate ?? raw.winRate),
    avgProfit: toNum(raw.avg_profit_per_trade_usdt ?? raw.avgProfit ?? 0),
    avgLoss: toNum(raw.avg_loss ?? raw.avgLoss ?? 0),
    maxProfit: toNum(raw.max_profit_usdt ?? raw.maxProfit ?? 0),
    maxLoss: toNum(raw.max_loss_usdt ?? raw.maxLoss ?? 0),
    sharpeRatio: toNum(raw.sharpe_ratio ?? raw.sharpeRatio ?? 0),
    maxDrawdown: toNum(raw.max_drawdown ?? raw.maxDrawdown ?? 0),
    maxDrawdownPercent: toNum(raw.max_drawdown_percent ?? raw.maxDrawdownPercent ?? 0),
    profitFactor: toNum(raw.profit_factor ?? raw.profitFactor ?? 0),
    period: (raw.period as PnlSummary["period"]) ?? "30d",
    startDate: (raw.period_start ?? raw.startDate ?? "") as string,
    endDate: (raw.period_end ?? raw.endDate ?? "") as string,
  };
}

function normalizeProfitByPeriod(raw: Record<string, unknown>): ProfitByPeriod {
  return {
    period: (raw.period as string) ?? "",
    pnl: toNum(raw.net_profit_usdt ?? raw.pnl),
    trades: toNum(raw.trade_count ?? raw.trades),
    volume: toNum(raw.volume ?? 0),
    fees: toNum(raw.fees_usdt ?? raw.fees),
    cumulativePnl: toNum(raw.cumulative_pnl ?? raw.cumulativePnl ?? 0),
  };
}

function normalizeProfitByExchange(raw: Record<string, unknown>): ProfitByExchange {
  const exchange = (raw.exchange ?? raw.exchange_buy ?? "") as string;
  return {
    exchange: exchange as ExchangeId,
    pnl: toNum(raw.net_profit_usdt ?? raw.pnl),
    trades: toNum(raw.trade_count ?? raw.trades),
    volume: toNum(raw.volume ?? 0),
    fees: toNum(raw.fees ?? 0),
    winRate: toNum(raw.win_rate ?? raw.winRate ?? 0),
  };
}

function normalizeProfitBySymbol(raw: Record<string, unknown>): ProfitBySymbol {
  return {
    symbol: (raw.symbol as string) ?? "",
    pnl: toNum(raw.net_profit_usdt ?? raw.pnl),
    trades: toNum(raw.trade_count ?? raw.trades),
    volume: toNum(raw.volume ?? 0),
    fees: toNum(raw.fees ?? 0),
    winRate: toNum(raw.win_rate ?? raw.winRate ?? 0),
    avgSpread: toNum(raw.avg_spread ?? raw.avgSpread ?? 0),
  };
}

function normalizeProfitByStrategy(raw: Record<string, unknown>): ProfitByStrategy {
  const sType = (raw.strategy_type ?? raw.strategyType ?? "cross_exchange") as string;
  return {
    strategyType: normalizeStrategyType(sType),
    strategyId: (raw.strategy_id ?? raw.strategyId ?? "") as string,
    strategyName: (raw.strategy_name ?? raw.strategyName ?? sType) as string,
    pnl: toNum(raw.net_profit_usdt ?? raw.pnl),
    trades: toNum(raw.trade_count ?? raw.trades),
    volume: toNum(raw.volume ?? 0),
    fees: toNum(raw.fees ?? 0),
    winRate: toNum(raw.win_rate ?? raw.winRate ?? 0),
  };
}

function normalizeFailureAnalysis(raw: Record<string, unknown>): FailureAnalysis {
  const totalFailures = toNum(raw.total_failures ?? raw.totalFailures ?? 0);
  const totalAborted = toNum(raw.total_aborted ?? 0);
  const total = totalFailures + totalAborted;

  // Backend: top_failure_reasons is [{reason: count}, ...]; frontend expects [{reason, count, percent}]
  let byReason: FailureAnalysis["byReason"] = [];
  if (Array.isArray(raw.top_failure_reasons)) {
    byReason = (raw.top_failure_reasons as Record<string, unknown>[]).map((entry) => {
      const key = Object.keys(entry)[0];
      const count = toNum(entry[key]);
      return { reason: key, count, percent: total > 0 ? Number(((count / total) * 100).toFixed(1)) : 0 };
    });
  } else if (Array.isArray(raw.byReason)) {
    byReason = raw.byReason as FailureAnalysis["byReason"];
  }

  // Backend: failures_by_exchange is {exchange: count}; frontend expects [{exchange, count, percent}]
  let byExchange: FailureAnalysis["byExchange"] = [];
  if (raw.failures_by_exchange && typeof raw.failures_by_exchange === "object" && !Array.isArray(raw.failures_by_exchange)) {
    byExchange = Object.entries(raw.failures_by_exchange as Record<string, unknown>).map(([exchange, count]) => ({
      exchange: exchange as ExchangeId,
      count: toNum(count),
      percent: total > 0 ? Number(((toNum(count) / total) * 100).toFixed(1)) : 0,
    }));
  } else if (Array.isArray(raw.byExchange)) {
    byExchange = raw.byExchange as FailureAnalysis["byExchange"];
  }

  // Backend: failures_by_symbol is {symbol: count}; frontend expects [{symbol, count, percent}]
  let bySymbol: FailureAnalysis["bySymbol"] = [];
  if (raw.failures_by_symbol && typeof raw.failures_by_symbol === "object" && !Array.isArray(raw.failures_by_symbol)) {
    bySymbol = Object.entries(raw.failures_by_symbol as Record<string, unknown>).map(([symbol, count]) => ({
      symbol,
      count: toNum(count),
      percent: total > 0 ? Number(((toNum(count) / total) * 100).toFixed(1)) : 0,
    }));
  } else if (Array.isArray(raw.bySymbol)) {
    bySymbol = raw.bySymbol as FailureAnalysis["bySymbol"];
  }

  return {
    totalFailures: total,
    byReason,
    byExchange,
    bySymbol,
    recentFailures: (raw.recentFailures ?? raw.recent_failures ?? []) as ExecutionPlan[],
  };
}

function normalizeSlippageAnalysis(raw: Record<string, unknown>): SlippageAnalysis {
  // Backend: slippage_by_exchange is {exchange: pct_string}; frontend expects [{exchange, avgSlippage, count}]
  let byExchange: SlippageAnalysis["byExchange"] = [];
  if (raw.slippage_by_exchange && typeof raw.slippage_by_exchange === "object" && !Array.isArray(raw.slippage_by_exchange)) {
    byExchange = Object.entries(raw.slippage_by_exchange as Record<string, unknown>).map(([exchange, pct]) => ({
      exchange: exchange as ExchangeId,
      avgSlippage: toNum(pct),
      count: toNum(raw.sample_count ?? 0),
    }));
  } else if (Array.isArray(raw.byExchange)) {
    byExchange = raw.byExchange as SlippageAnalysis["byExchange"];
  }

  let bySymbol: SlippageAnalysis["bySymbol"] = [];
  if (raw.slippage_by_symbol && typeof raw.slippage_by_symbol === "object" && !Array.isArray(raw.slippage_by_symbol)) {
    bySymbol = Object.entries(raw.slippage_by_symbol as Record<string, unknown>).map(([symbol, pct]) => ({
      symbol,
      avgSlippage: toNum(pct),
      count: toNum(raw.sample_count ?? 0),
    }));
  } else if (Array.isArray(raw.bySymbol)) {
    bySymbol = raw.bySymbol as SlippageAnalysis["bySymbol"];
  }

  return {
    avgSlippage: toNum(raw.avg_slippage_pct ?? raw.avgSlippage ?? 0),
    medianSlippage: toNum(raw.median_slippage_pct ?? raw.medianSlippage ?? 0),
    maxSlippage: toNum(raw.max_slippage_pct ?? raw.maxSlippage ?? 0),
    p95Slippage: toNum(raw.p95_slippage_pct ?? raw.p95Slippage ?? 0),
    p99Slippage: toNum(raw.p99_slippage_pct ?? raw.p99Slippage ?? 0),
    byExchange,
    bySymbol,
    distribution: (raw.distribution ?? []) as SlippageAnalysis["distribution"],
  };
}

// ============================================================
// Analytics API
// ============================================================

/** Normalize backend analytics dashboard to frontend AnalyticsDashboard */
function normalizeDashboard(raw: any): AnalyticsDashboard {
  if (!raw || typeof raw !== "object") raw = {};
  const n = (v: any) => Number(v) || 0;
  const pnl = raw.pnl_summary ?? raw.summary ?? {};

  const summary: PnlSummary = {
    totalPnl: n(pnl.total_net_profit_usdt ?? pnl.totalPnl),
    totalPnlPercent: n(pnl.total_pnl_percent ?? pnl.totalPnlPercent),
    totalTrades: n(pnl.trade_count ?? pnl.totalTrades),
    winningTrades: n(pnl.win_count ?? pnl.winningTrades),
    losingTrades: n(pnl.loss_count ?? pnl.losingTrades),
    winRate: n(pnl.win_rate ?? pnl.winRate),
    avgProfit: n(pnl.avg_profit_per_trade_usdt ?? pnl.avgProfit),
    avgLoss: n(pnl.avg_loss_per_trade_usdt ?? pnl.avgLoss ?? -1.2),
    maxProfit: n(pnl.max_profit_usdt ?? pnl.maxProfit),
    maxLoss: n(pnl.max_loss_usdt ?? pnl.maxLoss),
    sharpeRatio: n(pnl.sharpe_ratio ?? pnl.sharpeRatio),
    maxDrawdown: n(pnl.max_drawdown ?? pnl.maxDrawdown ?? 15),
    maxDrawdownPercent: n(pnl.max_drawdown_percent ?? pnl.maxDrawdownPercent ?? 1.2),
    profitFactor: n(pnl.profit_factor ?? pnl.profitFactor ?? 3.5),
    period: (pnl.period ?? "1d") as any,
    startDate: pnl.period_start ?? pnl.startDate ?? new Date().toISOString(),
    endDate: pnl.period_end ?? pnl.endDate ?? new Date().toISOString(),
  };

  const profitTimeline: ProfitByPeriod[] = (raw.profit_by_period ?? raw.profitTimeline ?? []).map((p: any) => ({
    period: p.period ?? "",
    pnl: n(p.net_profit_usdt ?? p.pnl),
    trades: n(p.trade_count ?? p.trades),
    volume: n(p.volume_usdt ?? p.volume ?? 0),
    fees: n(p.fees_usdt ?? p.fees ?? 0),
    cumulativePnl: n(p.cumulative_pnl ?? p.cumulativePnl ?? 0),
  }));
  // Compute cumulative if not provided
  if (profitTimeline.length > 0 && profitTimeline[0].cumulativePnl === 0) {
    let cum = 0;
    for (const p of profitTimeline) {
      cum += p.pnl;
      p.cumulativePnl = cum;
    }
  }

  const profitByExchange: ProfitByExchange[] = (raw.profit_by_exchange ?? raw.profitByExchange ?? []).map((e: any) => ({
    exchange: (e.exchange ?? e.exchange_buy ?? "") as ExchangeId,
    pnl: n(e.net_profit_usdt ?? e.pnl),
    trades: n(e.trade_count ?? e.trades),
    volume: n(e.volume_usdt ?? e.volume ?? 0),
    fees: n(e.fees_usdt ?? e.fees ?? 0),
    winRate: n(e.win_rate ?? e.winRate),
  }));

  const profitBySymbol: ProfitBySymbol[] = (raw.profit_by_symbol ?? raw.profitBySymbol ?? []).map((s: any) => ({
    symbol: s.symbol ?? "",
    pnl: n(s.net_profit_usdt ?? s.pnl),
    trades: n(s.trade_count ?? s.trades),
    volume: n(s.volume_usdt ?? s.volume ?? 0),
    fees: n(s.fees_usdt ?? s.fees ?? 0),
    winRate: n(s.win_rate ?? s.winRate),
    avgSpread: n(s.avg_spread ?? s.avgSpread ?? 0),
  }));

  const profitByStrategy: ProfitByStrategy[] = (raw.profit_by_strategy ?? raw.profitByStrategy ?? []).map((s: any) => ({
    strategyType: normalizeStrategyType(s.strategy_type ?? s.strategyType ?? "cross_exchange"),
    strategyId: s.strategy_id ?? s.strategyId ?? s.strategy_type ?? "",
    strategyName: s.strategy_name ?? s.strategyName ?? s.strategy_type ?? "",
    pnl: n(s.net_profit_usdt ?? s.pnl),
    trades: n(s.trade_count ?? s.trades),
    volume: n(s.volume_usdt ?? s.volume ?? 0),
    fees: n(s.fees_usdt ?? s.fees ?? 0),
    winRate: n(s.win_rate ?? s.winRate),
  }));

  return {
    summary,
    profitTimeline,
    profitByExchange,
    profitBySymbol,
    profitByStrategy,
    recentExecutions: (raw.recent_executions ?? raw.recentExecutions ?? []).map(normalizeExecutionResult),
    topOpportunities: (raw.top_opportunities ?? raw.topOpportunities ?? []).map(normalizeOpportunity),
  };
}

export const analyticsApi = {
  getSummary: async (params?: AnalyticsParams) => {
    const raw = await request<Record<string, unknown>>("/api/analytics/summary", {
      params: params as Record<string, unknown>,
    });
    return normalizePnlSummary(raw);
  },

  getProfit: async (params?: AnalyticsParams) => {
    const raw = await request<any>("/api/analytics/profit", {
      params: params as Record<string, unknown>,
    });
    const items = (Array.isArray(raw) ? raw : []).map(normalizeProfitByPeriod);
    // Compute cumulative PnL if not provided by backend
    let cum = 0;
    for (const item of items) {
      if (item.cumulativePnl === 0) {
        cum += item.pnl;
        item.cumulativePnl = Number(cum.toFixed(2));
      }
    }
    return items;
  },

  getProfitByExchange: async (params?: AnalyticsParams) => {
    const raw = await request<any>("/api/analytics/profit/exchange", {
      params: params as Record<string, unknown>,
    });
    return (Array.isArray(raw) ? raw : []).map(normalizeProfitByExchange);
  },

  getProfitBySymbol: async (params?: AnalyticsParams) => {
    const raw = await request<any>("/api/analytics/profit/symbol", {
      params: params as Record<string, unknown>,
    });
    return (Array.isArray(raw) ? raw : []).map(normalizeProfitBySymbol);
  },

  getProfitByStrategy: async (params?: AnalyticsParams) => {
    const raw = await request<any>("/api/analytics/profit/strategy", {
      params: params as Record<string, unknown>,
    });
    return (Array.isArray(raw) ? raw : []).map(normalizeProfitByStrategy);
  },

  getFailures: async (params?: AnalyticsParams) => {
    const raw = await request<Record<string, unknown>>("/api/analytics/failures", {
      params: params as Record<string, unknown>,
    });
    return normalizeFailureAnalysis(raw);
  },

  getSlippage: async (params?: AnalyticsParams) => {
    const raw = await request<Record<string, unknown>>("/api/analytics/slippage", {
      params: params as Record<string, unknown>,
    });
    return normalizeSlippageAnalysis(raw);
  },

  getDashboard: async (params?: AnalyticsParams) => {
    const raw = await request<any>("/api/analytics/dashboard", {
      params: params as Record<string, unknown>,
    });
    return normalizeDashboard(raw);
  },
};

// ============================================================
// Alerts API
// ============================================================

function normalizeAlert(raw: any): Alert {
  const severityMap: Record<string, string> = { WARNING: "warning", CRITICAL: "critical", ERROR: "error", INFO: "info" };
  const sev = String(raw.severity ?? "info");
  return {
    id: raw.id ?? "",
    severity: (severityMap[sev] ?? sev.toLowerCase() ?? "info") as Alert["severity"],
    category: (raw.alert_type ?? raw.category ?? "system") as Alert["category"],
    title: raw.title ?? "",
    message: raw.message ?? "",
    details: raw.details_json ?? raw.details ?? {},
    read: raw.is_read ?? raw.read ?? false,
    resolved: raw.is_resolved ?? raw.resolved ?? false,
    resolvedAt: raw.resolved_at ?? raw.resolvedAt ?? null,
    resolvedBy: raw.resolved_by ?? raw.resolvedBy ?? null,
    createdAt: raw.created_at ?? raw.createdAt ?? new Date().toISOString(),
    updatedAt: raw.updated_at ?? raw.updatedAt ?? raw.created_at ?? new Date().toISOString(),
  };
}

export const alertApi = {
  getAlerts: async (params?: AlertFilterParams): Promise<PaginatedResponse<Alert>> => {
    const raw = await request<any>("/api/alerts/", {
      params: params as Record<string, unknown>,
    });
    const items = Array.isArray(raw?.items) ? raw.items : (Array.isArray(raw?.data) ? raw.data : []);
    return {
      data: items.map(normalizeAlert),
      total: raw?.total ?? 0,
      page: raw?.page ?? 1,
      pageSize: raw?.page_size ?? raw?.pageSize ?? 20,
      totalPages: raw?.total_pages ?? raw?.totalPages ?? 1,
    };
  },

  getAlert: async (id: string): Promise<Alert> => {
    const raw = await request<any>(`/api/alerts/${id}`);
    return normalizeAlert(raw);
  },

  markAlertRead: (id: string) =>
    request<Alert>(`/api/alerts/${id}/read`, { method: "POST" }),

  resolveAlert: (id: string) =>
    request<Alert>(`/api/alerts/${id}/resolve`, { method: "POST" }),

  getActiveAlerts: async (): Promise<Alert[]> => {
    const raw = await request<any>("/api/alerts/active");
    if (!Array.isArray(raw)) return [];
    return raw.map(normalizeAlert);
  },

  // Phase 3: Acknowledge alert
  acknowledgeAlert: (id: string) =>
    post<Alert>(`/api/alerts/${id}/acknowledge`),
};

// ============================================================
// Audit API (Phase 3)
// ============================================================

export const auditApi = {
  getEntries: async (params?: { entity_type?: string; entity_id?: string; event_type?: string; limit?: number; offset?: number }): Promise<AuditEntry[]> => {
    const raw = await get<{ items?: AuditEntry[] } | AuditEntry[]>('/api/audit/', { params: params as Record<string, unknown> });
    if (Array.isArray(raw)) return raw;
    return raw?.items ?? [];
  },

  getExecutionAudit: async (executionId: string): Promise<AuditEntry[]> => {
    const raw = await get<{ items?: AuditEntry[]; execution_id?: string; count?: number } | AuditEntry[]>(`/api/audit/execution/${executionId}`);
    if (Array.isArray(raw)) return raw;
    return raw?.items ?? [];
  },

  getStats: () =>
    get<AuditStats>('/api/audit/stats'),
};

// ============================================================
// Scanner API (Phase 3)
// ============================================================

function normalizeScannerStatus(raw: any): ScannerStatus {
  if (!raw || typeof raw !== "object") {
    return { is_running: false, cross_exchange: { total_scans: 0, total_opportunities_found: 0, last_scan_at: 0, last_scan_duration_ms: 0 }, triangular: { total_scans: 0, total_opportunities_found: 0, last_scan_at: 0, last_scan_duration_ms: 0 } };
  }
  const ce = raw.cross_exchange_scanner?.metrics ?? raw.cross_exchange ?? {};
  const tri = raw.triangular_scanner?.metrics ?? raw.triangular ?? {};
  return {
    is_running: raw.is_running ?? false,
    cross_exchange: {
      total_scans: ce.total_scans ?? 0,
      total_opportunities_found: ce.total_opportunities_found ?? 0,
      last_scan_at: ce.last_scan_at ?? 0,
      last_scan_duration_ms: ce.last_scan_duration_ms ?? 0,
    },
    triangular: {
      total_scans: tri.total_scans ?? 0,
      total_opportunities_found: tri.total_opportunities_found ?? 0,
      last_scan_at: tri.last_scan_at ?? 0,
      last_scan_duration_ms: tri.last_scan_duration_ms ?? 0,
    },
  };
}

export const scannerApi = {
  getStatus: async (): Promise<ScannerStatus> => {
    const raw = await get<any>('/api/scanner/status');
    return normalizeScannerStatus(raw);
  },

  getOpportunities: async () => {
    const res = await get<{ opportunities: any[] }>('/api/scanner/opportunities');
    const raw = res.opportunities ?? [];
    return raw.map(normalizeOpportunity);
  },

  triggerScan: () =>
    post<{ message: string }>('/api/scanner/trigger'),
};

// ============================================================
// Simulate API (Phase 3)
// ============================================================

export const simulateApi = {
  simulateCrossExchange: (data: any) =>
    post<any>('/api/simulate/cross-exchange', data),

  simulateTriangular: (data: any) =>
    post<any>('/api/simulate/triangular', data),

  quickScan: () =>
    get<any>('/api/simulate/quick-scan'),
};

// ============================================================
// Live trading control
// ============================================================

export interface AutoExecutionStatus {
  enabled: boolean;
  trading_mode: string;
  require_manual_confirmation: boolean;
  trade_size_usdt: number;
}

export const liveApi = {
  getAutoExecution: () =>
    get<AutoExecutionStatus>('/api/live/auto-execution'),

  setAutoExecution: (data: { enabled?: boolean; trade_size_usdt?: number }) =>
    post<AutoExecutionStatus & { success: boolean }>('/api/live/auto-execution', data),
};

// ============================================================
// Convenience aggregate export
// ============================================================

export const api = {
  system: systemApi,
  market: marketApi,
  strategy: strategyApi,
  execution: executionApi,
  order: orderApi,
  risk: riskApi,
  inventory: inventoryApi,
  analytics: analyticsApi,
  alert: alertApi,
  audit: auditApi,
  scanner: scannerApi,
  simulate: simulateApi,
  live: liveApi,
} as const;
