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
  } catch {
    console.warn('API call failed, using mock data');
    return mockData;
  }
}

// ============================================================
// System API
// ============================================================

export const systemApi = {
  getHealth: () => request<SystemHealth>("/api/v1/system/health"),

  getMetrics: () => request<SystemMetrics>("/api/v1/system/metrics"),

  getExchanges: () => request<ExchangeStatus[]>("/api/v1/system/exchanges"),

  getWsStatus: () => request<WsStatus>("/api/v1/system/ws-status"),
};

// ============================================================
// Market API
// ============================================================

export const marketApi = {
  getTickers: (params?: { symbol?: string; exchange?: string }) =>
    request<Ticker[]>("/api/v1/market/tickers", { params }),

  getTicker: (exchange: string, symbol: string) =>
    request<Ticker>(`/api/v1/market/tickers/${exchange}/${symbol}`),

  getOrderbook: (exchange: string, symbol: string) =>
    request<Orderbook>(`/api/v1/market/orderbook/${exchange}/${symbol}`),

  getSpreads: (params?: { symbol?: string }) =>
    request<SpreadInfo[]>("/api/v1/market/spreads", { params }),

  getSpread: (symbol: string) =>
    request<SpreadInfo[]>(`/api/v1/market/spreads/${symbol}`),

  getOpportunities: (params?: OpportunityFilter) =>
    request<ArbitrageOpportunity[]>("/api/v1/market/opportunities", {
      params: params as Record<string, unknown>,
    }),
};

// ============================================================
// Strategy API
// ============================================================

export const strategyApi = {
  getStrategies: () =>
    request<StrategyConfig[]>("/api/v1/strategies"),

  getStrategy: (id: string) =>
    request<StrategyConfig>(`/api/v1/strategies/${id}`),

  updateStrategy: (id: string, data: Partial<StrategyConfig>) =>
    request<StrategyConfig>(`/api/v1/strategies/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  enableStrategy: (id: string) =>
    request<StrategyConfig>(`/api/v1/strategies/${id}/enable`, {
      method: "POST",
    }),

  disableStrategy: (id: string) =>
    request<StrategyConfig>(`/api/v1/strategies/${id}/disable`, {
      method: "POST",
    }),
};

// ============================================================
// Execution API
// ============================================================

export const executionApi = {
  getExecutions: (params?: ExecutionFilterParams) =>
    request<PaginatedResponse<ExecutionPlan>>("/api/v1/executions", {
      params: params as Record<string, unknown>,
    }),

  getExecution: (id: string) =>
    request<ExecutionPlan>(`/api/v1/executions/${id}`),

  getActiveExecutions: () =>
    request<ExecutionPlan[]>("/api/v1/executions/active"),

  triggerExecution: (opportunityId: string) =>
    request<ExecutionPlan>("/api/v1/executions/trigger", {
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
};

// ============================================================
// Order API
// ============================================================

export const orderApi = {
  getOrders: (params?: OrderFilterParams) =>
    request<PaginatedResponse<Order>>("/api/v1/orders", {
      params: params as Record<string, unknown>,
    }),

  getOrder: (id: string) => request<Order>(`/api/v1/orders/${id}`),
};

// ============================================================
// Risk API
// ============================================================

export const riskApi = {
  getRiskRules: () => request<RiskRule[]>("/api/v1/risk/rules"),

  updateRiskRule: (id: string, data: Partial<RiskRule>) =>
    request<RiskRule>(`/api/v1/risk/rules/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getRiskEvents: (params?: { severity?: string; limit?: number }) =>
    request<RiskEvent[]>("/api/v1/risk/events", { params }),

  getExposure: () => request<RiskExposure>("/api/v1/risk/exposure"),

  // Phase 3: Risk check
  checkRisk: (data: { symbol: string; buy_exchange: string; sell_exchange: string; buy_price: number; sell_price: number; quantity: number; estimated_profit_pct: number }) =>
    post<RiskDecision>('/api/risk/check', data),
};

// ============================================================
// Inventory API
// ============================================================

export const inventoryApi = {
  getBalances: (params?: { exchange?: string; asset?: string }) =>
    request<Balance[]>("/api/v1/inventory/balances", { params }),

  getExchangeBalances: (exchange: string) =>
    request<ExchangeAllocation>(`/api/v1/inventory/balances/${exchange}`),

  getAllocation: () =>
    request<InventorySummary>("/api/v1/inventory/allocation"),

  getRebalanceSuggestions: () =>
    request<RebalanceSuggestion[]>("/api/v1/inventory/rebalance"),

  // Phase 3: Enhanced inventory endpoints
  getExposure: () =>
    get<ExposureData>('/api/inventory/exposure'),

  getSummary: () =>
    get<InventoryFullSummary>('/api/inventory/summary'),
};

// ============================================================
// Analytics API
// ============================================================

export const analyticsApi = {
  getSummary: (params?: AnalyticsParams) =>
    request<PnlSummary>("/api/v1/analytics/summary", {
      params: params as Record<string, unknown>,
    }),

  getProfit: (params?: AnalyticsParams) =>
    request<ProfitByPeriod[]>("/api/v1/analytics/profit", {
      params: params as Record<string, unknown>,
    }),

  getProfitByExchange: (params?: AnalyticsParams) =>
    request<ProfitByExchange[]>("/api/v1/analytics/profit/exchange", {
      params: params as Record<string, unknown>,
    }),

  getProfitBySymbol: (params?: AnalyticsParams) =>
    request<ProfitBySymbol[]>("/api/v1/analytics/profit/symbol", {
      params: params as Record<string, unknown>,
    }),

  getProfitByStrategy: (params?: AnalyticsParams) =>
    request<ProfitByStrategy[]>("/api/v1/analytics/profit/strategy", {
      params: params as Record<string, unknown>,
    }),

  getFailures: (params?: AnalyticsParams) =>
    request<FailureAnalysis>("/api/v1/analytics/failures", {
      params: params as Record<string, unknown>,
    }),

  getSlippage: (params?: AnalyticsParams) =>
    request<SlippageAnalysis>("/api/v1/analytics/slippage", {
      params: params as Record<string, unknown>,
    }),

  getDashboard: (params?: AnalyticsParams) =>
    request<AnalyticsDashboard>("/api/v1/analytics/dashboard", {
      params: params as Record<string, unknown>,
    }),
};

// ============================================================
// Alerts API
// ============================================================

export const alertApi = {
  getAlerts: (params?: AlertFilterParams) =>
    request<PaginatedResponse<Alert>>("/api/v1/alerts", {
      params: params as Record<string, unknown>,
    }),

  getAlert: (id: string) => request<Alert>(`/api/v1/alerts/${id}`),

  markAlertRead: (id: string) =>
    request<Alert>(`/api/v1/alerts/${id}/read`, { method: "POST" }),

  resolveAlert: (id: string) =>
    request<Alert>(`/api/v1/alerts/${id}/resolve`, { method: "POST" }),

  getActiveAlerts: () =>
    request<Alert[]>("/api/v1/alerts/active"),

  // Phase 3: Acknowledge alert
  acknowledgeAlert: (id: string) =>
    post<Alert>(`/api/alerts/${id}/acknowledge`),
};

// ============================================================
// Audit API (Phase 3)
// ============================================================

export const auditApi = {
  getEntries: (params?: { entity_type?: string; entity_id?: string; event_type?: string; limit?: number; offset?: number }) =>
    get<AuditEntry[]>('/api/audit/', { params: params as Record<string, unknown> }),

  getExecutionAudit: (executionId: string) =>
    get<AuditEntry[]>(`/api/audit/execution/${executionId}`),

  getStats: () =>
    get<AuditStats>('/api/audit/stats'),
};

// ============================================================
// Scanner API (Phase 3)
// ============================================================

export const scannerApi = {
  getStatus: () =>
    get<ScannerStatus>('/api/scanner/status'),

  getOpportunities: () =>
    get<ArbitrageOpportunity[]>('/api/scanner/opportunities'),

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
} as const;
