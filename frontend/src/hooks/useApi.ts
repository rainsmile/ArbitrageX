"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import {
  systemApi,
  marketApi,
  strategyApi,
  executionApi,
  orderApi,
  riskApi,
  inventoryApi,
  analyticsApi,
  alertApi,
  auditApi,
  scannerApi,
  simulateApi,
  withMockFallback,
} from "@/lib/api";
import {
  mockSystemHealth,
  mockSystemMetrics,
  mockExchanges,
  mockWsStatus,
  mockTickers,
  mockSpreads,
  mockOpportunities,
  mockStrategies,
  mockExecutions,
  mockOrders,
  mockRiskRules,
  mockRiskEvents,
  mockExposure as mockRiskExposure,
  mockBalances,
  mockAllocations,
  mockInventorySummary,
  mockRebalanceSuggestions,
  mockPnlSummary,
  mockProfitTimeline,
  mockProfitByExchange,
  mockProfitBySymbol,
  mockProfitByStrategy,
  mockFailureAnalysis,
  mockSlippageAnalysis,
  mockDashboard,
  mockAlerts,
  mockExecutionDetails,
  mockRiskDecision,
  mockInventoryExposure,
  mockScannerStatus,
  mockAuditEntries,
  mockAuditStats,
  mockInventoryFullSummary,
} from "@/lib/mock-data";
import type {
  AlertFilterParams,
  AnalyticsParams,
  ExecutionFilterParams,
  OpportunityFilter,
  OrderFilterParams,
  StrategyConfig,
  RiskRule,
} from "@/types";

// ============================================================
// Query key factory
// ============================================================

export const queryKeys = {
  system: {
    health: ["system", "health"] as const,
    metrics: ["system", "metrics"] as const,
    exchanges: ["system", "exchanges"] as const,
    wsStatus: ["system", "wsStatus"] as const,
  },
  market: {
    tickers: (params?: Record<string, string>) =>
      ["market", "tickers", params] as const,
    ticker: (exchange: string, symbol: string) =>
      ["market", "ticker", exchange, symbol] as const,
    orderbook: (exchange: string, symbol: string) =>
      ["market", "orderbook", exchange, symbol] as const,
    spreads: (params?: Record<string, string>) =>
      ["market", "spreads", params] as const,
    spread: (symbol: string) => ["market", "spread", symbol] as const,
    opportunities: (params?: OpportunityFilter) =>
      ["market", "opportunities", params] as const,
  },
  strategies: {
    all: ["strategies"] as const,
    detail: (id: string) => ["strategies", id] as const,
  },
  executions: {
    list: (params?: ExecutionFilterParams) =>
      ["executions", "list", params] as const,
    detail: (id: string) => ["executions", id] as const,
    active: ["executions", "active"] as const,
    activeDetail: ["executions", "activeDetail"] as const,
    executionDetail: (id: string) => ["executions", "detail", id] as const,
  },
  orders: {
    list: (params?: OrderFilterParams) => ["orders", "list", params] as const,
    detail: (id: string) => ["orders", id] as const,
  },
  risk: {
    rules: ["risk", "rules"] as const,
    events: (params?: Record<string, unknown>) =>
      ["risk", "events", params] as const,
    exposure: ["risk", "exposure"] as const,
  },
  inventory: {
    balances: (params?: Record<string, string>) =>
      ["inventory", "balances", params] as const,
    exchangeBalances: (exchange: string) =>
      ["inventory", "balances", exchange] as const,
    allocation: ["inventory", "allocation"] as const,
    rebalance: ["inventory", "rebalance"] as const,
    exposure: ["inventory", "exposure"] as const,
    summary: ["inventory", "summary"] as const,
  },
  analytics: {
    summary: (params?: AnalyticsParams) =>
      ["analytics", "summary", params] as const,
    profit: (params?: AnalyticsParams) =>
      ["analytics", "profit", params] as const,
    profitByExchange: (params?: AnalyticsParams) =>
      ["analytics", "profitByExchange", params] as const,
    profitBySymbol: (params?: AnalyticsParams) =>
      ["analytics", "profitBySymbol", params] as const,
    profitByStrategy: (params?: AnalyticsParams) =>
      ["analytics", "profitByStrategy", params] as const,
    failures: (params?: AnalyticsParams) =>
      ["analytics", "failures", params] as const,
    slippage: (params?: AnalyticsParams) =>
      ["analytics", "slippage", params] as const,
    dashboard: (params?: AnalyticsParams) =>
      ["analytics", "dashboard", params] as const,
  },
  alerts: {
    list: (params?: AlertFilterParams) =>
      ["alerts", "list", params] as const,
    detail: (id: string) => ["alerts", id] as const,
    active: ["alerts", "active"] as const,
  },
  scanner: {
    status: ["scanner", "status"] as const,
    opportunities: ["scanner", "opportunities"] as const,
  },
  audit: {
    entries: (params?: Record<string, unknown>) =>
      ["audit", "entries", params] as const,
    executionAudit: (executionId: string) =>
      ["audit", "execution", executionId] as const,
    stats: ["audit", "stats"] as const,
  },
} as const;

// ============================================================
// Helper to merge common defaults
// ============================================================

type QueryOpts<T> = Omit<UseQueryOptions<T>, "queryKey" | "queryFn">;

// ============================================================
// System hooks
// ============================================================

export function useSystemHealth(opts?: QueryOpts<Awaited<ReturnType<typeof systemApi.getHealth>>>) {
  return useQuery({
    queryKey: queryKeys.system.health,
    queryFn: () => withMockFallback(() => systemApi.getHealth(), mockSystemHealth),
    refetchInterval: 10_000,
    staleTime: 5_000,
    ...opts,
  });
}

// Keep old name as alias
export const useHealth = useSystemHealth;

export function useSystemMetrics(opts?: QueryOpts<Awaited<ReturnType<typeof systemApi.getMetrics>>>) {
  return useQuery({
    queryKey: queryKeys.system.metrics,
    queryFn: () => withMockFallback(() => systemApi.getMetrics(), mockSystemMetrics),
    refetchInterval: 5_000,
    staleTime: 3_000,
    ...opts,
  });
}

// Keep old name as alias
export const useMetrics = useSystemMetrics;

export function useExchanges(opts?: QueryOpts<Awaited<ReturnType<typeof systemApi.getExchanges>>>) {
  return useQuery({
    queryKey: queryKeys.system.exchanges,
    queryFn: () => withMockFallback(() => systemApi.getExchanges(), mockExchanges),
    refetchInterval: 15_000,
    staleTime: 10_000,
    ...opts,
  });
}

export function useWsStatus(opts?: QueryOpts<Awaited<ReturnType<typeof systemApi.getWsStatus>>>) {
  return useQuery({
    queryKey: queryKeys.system.wsStatus,
    queryFn: () => withMockFallback(() => systemApi.getWsStatus(), mockWsStatus),
    refetchInterval: 10_000,
    staleTime: 5_000,
    ...opts,
  });
}

// ============================================================
// Market hooks
// ============================================================

export function useMarketTickers(
  exchange?: string,
  symbol?: string,
  opts?: QueryOpts<Awaited<ReturnType<typeof marketApi.getTickers>>>
) {
  const params = exchange || symbol ? { exchange, symbol } : undefined;
  return useQuery({
    queryKey: queryKeys.market.tickers(params as Record<string, string> | undefined),
    queryFn: () => withMockFallback(() => marketApi.getTickers(params), mockTickers),
    refetchInterval: 5_000,
    staleTime: 2_000,
    ...opts,
  });
}

// Keep old name as alias
export const useTickers = (
  params?: { symbol?: string; exchange?: string },
  opts?: QueryOpts<Awaited<ReturnType<typeof marketApi.getTickers>>>
) => {
  return useQuery({
    queryKey: queryKeys.market.tickers(params as Record<string, string> | undefined),
    queryFn: () => withMockFallback(() => marketApi.getTickers(params), mockTickers),
    refetchInterval: 3_000,
    staleTime: 2_000,
    ...opts,
  });
};

export function useTicker(
  exchange: string,
  symbol: string,
  opts?: QueryOpts<Awaited<ReturnType<typeof marketApi.getTicker>>>
) {
  return useQuery({
    queryKey: queryKeys.market.ticker(exchange, symbol),
    queryFn: () => withMockFallback(
      () => marketApi.getTicker(exchange, symbol),
      mockTickers.find((t) => t.exchange === exchange && t.symbol === symbol) ?? mockTickers[0]
    ),
    refetchInterval: 2_000,
    staleTime: 1_000,
    ...opts,
  });
}

export function useOrderbook(
  exchange: string,
  symbol: string,
  opts?: QueryOpts<Awaited<ReturnType<typeof marketApi.getOrderbook>>>
) {
  return useQuery({
    queryKey: queryKeys.market.orderbook(exchange, symbol),
    queryFn: () => marketApi.getOrderbook(exchange, symbol),
    refetchInterval: 1_000,
    ...opts,
  });
}

export function useMarketSpreads(
  params?: { symbol?: string },
  opts?: QueryOpts<Awaited<ReturnType<typeof marketApi.getSpreads>>>
) {
  return useQuery({
    queryKey: queryKeys.market.spreads(params as Record<string, string> | undefined),
    queryFn: () => withMockFallback(() => marketApi.getSpreads(params), mockSpreads),
    refetchInterval: 3_000,
    staleTime: 2_000,
    ...opts,
  });
}

// Keep old name as alias
export const useSpreads = useMarketSpreads;

// ============================================================
// Scanner hooks (Phase 3)
// ============================================================

export function useScannerStatus() {
  return useQuery({
    queryKey: queryKeys.scanner.status,
    queryFn: () => withMockFallback(() => scannerApi.getStatus(), mockScannerStatus),
    refetchInterval: 2_000,
    staleTime: 1_000,
  });
}

export function useScannerOpportunities() {
  return useQuery({
    queryKey: queryKeys.scanner.opportunities,
    queryFn: () => withMockFallback(() => scannerApi.getOpportunities(), mockOpportunities),
    refetchInterval: 2_000,
    staleTime: 1_000,
  });
}

export function useTriggerScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => scannerApi.triggerScan(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.scanner.status });
      qc.invalidateQueries({ queryKey: queryKeys.scanner.opportunities });
    },
  });
}

// ============================================================
// Opportunities hooks
// ============================================================

export function useOpportunities(
  params?: OpportunityFilter,
  opts?: QueryOpts<Awaited<ReturnType<typeof marketApi.getOpportunities>>>
) {
  return useQuery({
    queryKey: queryKeys.market.opportunities(params),
    queryFn: () => withMockFallback(() => marketApi.getOpportunities(params), mockOpportunities),
    refetchInterval: 3_000,
    staleTime: 2_000,
    ...opts,
  });
}

// ============================================================
// Strategy hooks
// ============================================================

export function useStrategies(opts?: QueryOpts<Awaited<ReturnType<typeof strategyApi.getStrategies>>>) {
  return useQuery({
    queryKey: queryKeys.strategies.all,
    queryFn: () => withMockFallback(() => strategyApi.getStrategies(), mockStrategies),
    refetchInterval: 30_000,
    staleTime: 15_000,
    ...opts,
  });
}

export function useStrategy(
  id: string,
  opts?: QueryOpts<Awaited<ReturnType<typeof strategyApi.getStrategy>>>
) {
  return useQuery({
    queryKey: queryKeys.strategies.detail(id),
    queryFn: () => withMockFallback(
      () => strategyApi.getStrategy(id),
      mockStrategies.find((s) => s.id === id) ?? mockStrategies[0]
    ),
    ...opts,
  });
}

export function useUpdateStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<StrategyConfig> }) =>
      strategyApi.updateStrategy(id, data),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.strategies.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.strategies.all });
    },
  });
}

export function useEnableStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => strategyApi.enableStrategy(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.strategies.all });
    },
  });
}

export function useDisableStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => strategyApi.disableStrategy(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.strategies.all });
    },
  });
}

// ============================================================
// Execution hooks
// ============================================================

export function useExecutions(
  params?: ExecutionFilterParams,
  opts?: QueryOpts<Awaited<ReturnType<typeof executionApi.getExecutions>>>
) {
  return useQuery({
    queryKey: queryKeys.executions.list(params),
    queryFn: () => withMockFallback(
      () => executionApi.getExecutions(params),
      { data: mockExecutions, total: mockExecutions.length, page: 1, pageSize: 20, totalPages: 1 }
    ),
    refetchInterval: 5_000,
    staleTime: 3_000,
    ...opts,
  });
}

export function useExecution(
  id: string,
  opts?: QueryOpts<Awaited<ReturnType<typeof executionApi.getExecution>>>
) {
  return useQuery({
    queryKey: queryKeys.executions.detail(id),
    queryFn: () => withMockFallback(
      () => executionApi.getExecution(id),
      mockExecutions.find((e) => e.id === id) ?? mockExecutions[0]
    ),
    ...opts,
  });
}

export function useActiveExecutions(
  opts?: QueryOpts<Awaited<ReturnType<typeof executionApi.getActiveExecutions>>>
) {
  return useQuery({
    queryKey: queryKeys.executions.active,
    queryFn: () => withMockFallback(
      () => executionApi.getActiveExecutions(),
      mockExecutions.filter((e) => e.status === "executing")
    ),
    refetchInterval: 2_000,
    staleTime: 1_000,
    ...opts,
  });
}

export function useExecutionDetail(id: string) {
  return useQuery({
    queryKey: queryKeys.executions.executionDetail(id),
    queryFn: () => withMockFallback(
      () => executionApi.getExecutionDetail(id),
      mockExecutionDetails.find((e) => e.execution_id === id) ?? mockExecutionDetails[0]
    ),
    enabled: !!id,
    staleTime: 2_000,
  });
}

export function useExecuteOpportunity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ opportunityId, mode }: { opportunityId: string; mode?: string }) =>
      executionApi.executeOpportunity(opportunityId, mode),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.executions.active });
      qc.invalidateQueries({ queryKey: queryKeys.executions.activeDetail });
    },
  });
}

export function useExecuteCrossExchange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { symbol: string; buy_exchange: string; sell_exchange: string; quantity: number; mode?: string }) =>
      executionApi.executeCrossExchange(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.executions.active });
      qc.invalidateQueries({ queryKey: queryKeys.executions.activeDetail });
    },
  });
}

export function useTriggerExecution() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (opportunityId: string) =>
      executionApi.triggerExecution(opportunityId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.executions.active });
    },
  });
}

// ============================================================
// Order hooks
// ============================================================

export function useOrders(
  params?: OrderFilterParams,
  opts?: QueryOpts<Awaited<ReturnType<typeof orderApi.getOrders>>>
) {
  return useQuery({
    queryKey: queryKeys.orders.list(params),
    queryFn: () => withMockFallback(
      () => orderApi.getOrders(params),
      { data: mockOrders, total: mockOrders.length, page: 1, pageSize: 20, totalPages: 1 }
    ),
    refetchInterval: 5_000,
    ...opts,
  });
}

export function useOrder(
  id: string,
  opts?: QueryOpts<Awaited<ReturnType<typeof orderApi.getOrder>>>
) {
  return useQuery({
    queryKey: queryKeys.orders.detail(id),
    queryFn: () => withMockFallback(
      () => orderApi.getOrder(id),
      mockOrders.find((o) => o.id === id) ?? mockOrders[0]
    ),
    ...opts,
  });
}

// ============================================================
// Risk hooks
// ============================================================

export function useRiskRules(opts?: QueryOpts<Awaited<ReturnType<typeof riskApi.getRiskRules>>>) {
  return useQuery({
    queryKey: queryKeys.risk.rules,
    queryFn: () => withMockFallback(() => riskApi.getRiskRules(), mockRiskRules),
    refetchInterval: 30_000,
    staleTime: 15_000,
    ...opts,
  });
}

export function useUpdateRiskRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<RiskRule> }) =>
      riskApi.updateRiskRule(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.risk.rules });
    },
  });
}

export function useRiskEvents(params?: { severity?: string; limit?: number }) {
  return useQuery({
    queryKey: queryKeys.risk.events(params),
    queryFn: () => withMockFallback(() => riskApi.getRiskEvents(params), mockRiskEvents),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}

export function useRiskExposure(opts?: QueryOpts<Awaited<ReturnType<typeof riskApi.getExposure>>>) {
  return useQuery({
    queryKey: queryKeys.risk.exposure,
    queryFn: () => withMockFallback(() => riskApi.getExposure(), mockRiskExposure),
    refetchInterval: 5_000,
    staleTime: 3_000,
    ...opts,
  });
}

// Keep old name as alias
export const useExposure = useRiskExposure;

export function useRiskCheck() {
  return useMutation({
    mutationFn: (data: { symbol: string; buy_exchange: string; sell_exchange: string; buy_price: number; sell_price: number; quantity: number; estimated_profit_pct: number }) =>
      riskApi.checkRisk(data),
  });
}

// ============================================================
// Inventory hooks
// ============================================================

export function useInventoryBalances(
  params?: { exchange?: string; asset?: string },
  opts?: QueryOpts<Awaited<ReturnType<typeof inventoryApi.getBalances>>>
) {
  return useQuery({
    queryKey: queryKeys.inventory.balances(params as Record<string, string> | undefined),
    queryFn: () => withMockFallback(() => inventoryApi.getBalances(params), mockBalances),
    refetchInterval: 15_000,
    staleTime: 10_000,
    ...opts,
  });
}

// Keep old name as alias
export const useBalances = useInventoryBalances;

export function useExchangeBalances(
  exchange: string,
  opts?: QueryOpts<Awaited<ReturnType<typeof inventoryApi.getExchangeBalances>>>
) {
  return useQuery({
    queryKey: queryKeys.inventory.exchangeBalances(exchange),
    queryFn: () => withMockFallback(
      () => inventoryApi.getExchangeBalances(exchange),
      mockAllocations.find((a) => a.exchange === exchange) ?? mockAllocations[0]
    ),
    refetchInterval: 15_000,
    staleTime: 10_000,
    ...opts,
  });
}

export function useAllocation(
  opts?: QueryOpts<Awaited<ReturnType<typeof inventoryApi.getAllocation>>>
) {
  return useQuery({
    queryKey: queryKeys.inventory.allocation,
    queryFn: () => withMockFallback(() => inventoryApi.getAllocation(), mockInventorySummary),
    refetchInterval: 30_000,
    staleTime: 15_000,
    ...opts,
  });
}

export function useRebalanceSuggestions(
  opts?: QueryOpts<Awaited<ReturnType<typeof inventoryApi.getRebalanceSuggestions>>>
) {
  return useQuery({
    queryKey: queryKeys.inventory.rebalance,
    queryFn: () => withMockFallback(() => inventoryApi.getRebalanceSuggestions(), mockRebalanceSuggestions),
    refetchInterval: 60_000,
    staleTime: 30_000,
    ...opts,
  });
}

export function useInventoryExposure() {
  return useQuery({
    queryKey: queryKeys.inventory.exposure,
    queryFn: () => withMockFallback(() => inventoryApi.getExposure(), mockInventoryExposure),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}

export function useInventorySummary() {
  return useQuery({
    queryKey: queryKeys.inventory.summary,
    queryFn: () => withMockFallback(() => inventoryApi.getSummary(), mockInventoryFullSummary),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}

// ============================================================
// Analytics hooks
// ============================================================

export function useAnalyticsSummary(hours?: number, params?: AnalyticsParams) {
  const fullParams = hours ? { ...params, interval: `${hours}h` as any } : params;
  return useQuery({
    queryKey: queryKeys.analytics.summary(fullParams),
    queryFn: () => withMockFallback(() => analyticsApi.getSummary(fullParams), mockPnlSummary),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useProfitByPeriod(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.profit(params),
    queryFn: () => withMockFallback(() => analyticsApi.getProfit(params), mockProfitTimeline),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

// Keep old name as alias
export const useProfit = useProfitByPeriod;

export function useProfitByExchange(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.profitByExchange(params),
    queryFn: () => withMockFallback(() => analyticsApi.getProfitByExchange(params), mockProfitByExchange),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useProfitBySymbol(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.profitBySymbol(params),
    queryFn: () => withMockFallback(() => analyticsApi.getProfitBySymbol(params), mockProfitBySymbol),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useProfitByStrategy(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.profitByStrategy(params),
    queryFn: () => withMockFallback(() => analyticsApi.getProfitByStrategy(params), mockProfitByStrategy),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useFailureAnalysis(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.failures(params),
    queryFn: () => withMockFallback(() => analyticsApi.getFailures(params), mockFailureAnalysis),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

// Keep old name as alias
export const useFailures = useFailureAnalysis;

export function useSlippageAnalysis(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.slippage(params),
    queryFn: () => withMockFallback(() => analyticsApi.getSlippage(params), mockSlippageAnalysis),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

// Keep old name as alias
export const useSlippage = useSlippageAnalysis;

export function useAnalyticsDashboard(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.dashboard(params),
    queryFn: () => withMockFallback(() => analyticsApi.getDashboard(params), mockDashboard),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

// Keep old name as alias
export const useDashboard = useAnalyticsDashboard;

// ============================================================
// Alert hooks
// ============================================================

export function useAlerts(
  params?: AlertFilterParams,
  opts?: QueryOpts<Awaited<ReturnType<typeof alertApi.getAlerts>>>
) {
  return useQuery({
    queryKey: queryKeys.alerts.list(params),
    queryFn: () => withMockFallback(
      () => alertApi.getAlerts(params),
      { data: mockAlerts, total: mockAlerts.length, page: 1, pageSize: 20, totalPages: 1 }
    ),
    refetchInterval: 10_000,
    staleTime: 5_000,
    ...opts,
  });
}

export function useAlert(
  id: string,
  opts?: QueryOpts<Awaited<ReturnType<typeof alertApi.getAlert>>>
) {
  return useQuery({
    queryKey: queryKeys.alerts.detail(id),
    queryFn: () => withMockFallback(
      () => alertApi.getAlert(id),
      mockAlerts.find((a) => a.id === id) ?? mockAlerts[0]
    ),
    ...opts,
  });
}

export function useActiveAlerts(
  opts?: QueryOpts<Awaited<ReturnType<typeof alertApi.getActiveAlerts>>>
) {
  return useQuery({
    queryKey: queryKeys.alerts.active,
    queryFn: () => withMockFallback(
      () => alertApi.getActiveAlerts(),
      mockAlerts.filter((a) => !a.resolved)
    ),
    refetchInterval: 5_000,
    staleTime: 3_000,
    ...opts,
  });
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => alertApi.acknowledgeAlert(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useMarkAlertRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => alertApi.markAlertRead(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useResolveAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => alertApi.resolveAlert(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

// ============================================================
// Audit hooks (Phase 3)
// ============================================================

export function useAuditEntries(params?: { entity_type?: string; entity_id?: string; event_type?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: queryKeys.audit.entries(params as Record<string, unknown> | undefined),
    queryFn: () => withMockFallback(() => auditApi.getEntries(params), mockAuditEntries),
    staleTime: 10_000,
  });
}

export function useExecutionAudit(executionId: string) {
  return useQuery({
    queryKey: queryKeys.audit.executionAudit(executionId),
    queryFn: () => withMockFallback(
      () => auditApi.getExecutionAudit(executionId),
      mockAuditEntries.filter((a) => a.entity_id === executionId)
    ),
    enabled: !!executionId,
    staleTime: 5_000,
  });
}

export function useAuditStats() {
  return useQuery({
    queryKey: queryKeys.audit.stats,
    queryFn: () => withMockFallback(() => auditApi.getStats(), mockAuditStats),
    staleTime: 30_000,
  });
}
