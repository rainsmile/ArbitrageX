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
  liveApi,
} from "@/lib/api";
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
    history: ["executions", "history"] as const,
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
    queryFn: () => systemApi.getHealth(),
    refetchInterval: 10_000,
    staleTime: 5_000,
    ...opts,
  });
}

export const useHealth = useSystemHealth;

export function useSystemMetrics(opts?: QueryOpts<Awaited<ReturnType<typeof systemApi.getMetrics>>>) {
  return useQuery({
    queryKey: queryKeys.system.metrics,
    queryFn: () => systemApi.getMetrics(),
    refetchInterval: 5_000,
    staleTime: 3_000,
    ...opts,
  });
}

export const useMetrics = useSystemMetrics;

export function useExchanges(opts?: QueryOpts<Awaited<ReturnType<typeof systemApi.getExchanges>>>) {
  return useQuery({
    queryKey: queryKeys.system.exchanges,
    queryFn: () => systemApi.getExchanges(),
    refetchInterval: 15_000,
    staleTime: 10_000,
    ...opts,
  });
}

export function useWsStatus(opts?: QueryOpts<Awaited<ReturnType<typeof systemApi.getWsStatus>>>) {
  return useQuery({
    queryKey: queryKeys.system.wsStatus,
    queryFn: () => systemApi.getWsStatus(),
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
    queryFn: () => marketApi.getTickers(params),
    refetchInterval: 5_000,
    staleTime: 2_000,
    ...opts,
  });
}

export const useTickers = (
  params?: { symbol?: string; exchange?: string },
  opts?: QueryOpts<Awaited<ReturnType<typeof marketApi.getTickers>>>
) => {
  return useQuery({
    queryKey: queryKeys.market.tickers(params as Record<string, string> | undefined),
    queryFn: () => marketApi.getTickers(params),
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
    queryFn: () => marketApi.getTicker(exchange, symbol),
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
    queryFn: () => marketApi.getSpreads(params),
    refetchInterval: 3_000,
    staleTime: 2_000,
    ...opts,
  });
}

export const useSpreads = useMarketSpreads;

// ============================================================
// Scanner hooks
// ============================================================

export function useScannerStatus() {
  return useQuery({
    queryKey: queryKeys.scanner.status,
    queryFn: () => scannerApi.getStatus(),
    refetchInterval: 2_000,
    staleTime: 1_000,
  });
}

export function useScannerOpportunities() {
  return useQuery({
    queryKey: queryKeys.scanner.opportunities,
    queryFn: () => scannerApi.getOpportunities(),
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
    queryFn: () => marketApi.getOpportunities(params),
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
    queryFn: () => strategyApi.getStrategies(),
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
    queryFn: () => strategyApi.getStrategy(id),
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
    queryFn: () => executionApi.getExecutions(params),
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
    queryFn: () => executionApi.getExecution(id),
    ...opts,
  });
}

export function useActiveExecutions(
  opts?: QueryOpts<Awaited<ReturnType<typeof executionApi.getActiveExecutions>>>
) {
  return useQuery({
    queryKey: queryKeys.executions.active,
    queryFn: () => executionApi.getActiveExecutions(),
    refetchInterval: 2_000,
    staleTime: 1_000,
    ...opts,
  });
}

export function useExecutionDetail(id: string) {
  return useQuery({
    queryKey: queryKeys.executions.executionDetail(id),
    queryFn: () => executionApi.getExecutionDetail(id),
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

export function useExecutionHistory() {
  return useQuery({
    queryKey: queryKeys.executions.history,
    queryFn: () => executionApi.getHistory(100),
    refetchInterval: 10_000,
    staleTime: 5_000,
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
    queryFn: () => orderApi.getOrders(params),
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
    queryFn: () => orderApi.getOrder(id),
    ...opts,
  });
}

// ============================================================
// Risk hooks
// ============================================================

export function useRiskRules(opts?: QueryOpts<Awaited<ReturnType<typeof riskApi.getRiskRules>>>) {
  return useQuery({
    queryKey: queryKeys.risk.rules,
    queryFn: () => riskApi.getRiskRules(),
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
    queryFn: () => riskApi.getRiskEvents(params),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}

export function useRiskExposure(opts?: QueryOpts<Awaited<ReturnType<typeof riskApi.getExposure>>>) {
  return useQuery({
    queryKey: queryKeys.risk.exposure,
    queryFn: () => riskApi.getExposure(),
    refetchInterval: 5_000,
    staleTime: 3_000,
    ...opts,
  });
}

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
    queryFn: () => inventoryApi.getBalances(params),
    refetchInterval: 15_000,
    staleTime: 10_000,
    ...opts,
  });
}

export const useBalances = useInventoryBalances;

export function useExchangeBalances(
  exchange: string,
  opts?: QueryOpts<Awaited<ReturnType<typeof inventoryApi.getExchangeBalances>>>
) {
  return useQuery({
    queryKey: queryKeys.inventory.exchangeBalances(exchange),
    queryFn: () => inventoryApi.getExchangeBalances(exchange),
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
    queryFn: () => inventoryApi.getAllocation(),
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
    queryFn: () => inventoryApi.getRebalanceSuggestions(),
    refetchInterval: 60_000,
    staleTime: 30_000,
    ...opts,
  });
}

export function useInventoryExposure() {
  return useQuery({
    queryKey: queryKeys.inventory.exposure,
    queryFn: () => inventoryApi.getExposure(),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}

export function useInventorySummary() {
  return useQuery({
    queryKey: queryKeys.inventory.summary,
    queryFn: () => inventoryApi.getSummary(),
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
    queryFn: () => analyticsApi.getSummary(fullParams),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useProfitByPeriod(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.profit(params),
    queryFn: () => analyticsApi.getProfit(params),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export const useProfit = useProfitByPeriod;

export function useProfitByExchange(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.profitByExchange(params),
    queryFn: () => analyticsApi.getProfitByExchange(params),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useProfitBySymbol(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.profitBySymbol(params),
    queryFn: () => analyticsApi.getProfitBySymbol(params),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useProfitByStrategy(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.profitByStrategy(params),
    queryFn: () => analyticsApi.getProfitByStrategy(params),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useFailureAnalysis(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.failures(params),
    queryFn: () => analyticsApi.getFailures(params),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export const useFailures = useFailureAnalysis;

export function useSlippageAnalysis(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.slippage(params),
    queryFn: () => analyticsApi.getSlippage(params),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export const useSlippage = useSlippageAnalysis;

export function useAnalyticsDashboard(params?: AnalyticsParams) {
  return useQuery({
    queryKey: queryKeys.analytics.dashboard(params),
    queryFn: () => analyticsApi.getDashboard(params),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

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
    queryFn: () => alertApi.getAlerts(params),
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
    queryFn: () => alertApi.getAlert(id),
    ...opts,
  });
}

export function useActiveAlerts(
  opts?: QueryOpts<Awaited<ReturnType<typeof alertApi.getActiveAlerts>>>
) {
  return useQuery({
    queryKey: queryKeys.alerts.active,
    queryFn: () => alertApi.getActiveAlerts(),
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
// Audit hooks
// ============================================================

export function useAuditEntries(params?: { entity_type?: string; entity_id?: string; event_type?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: queryKeys.audit.entries(params as Record<string, unknown> | undefined),
    queryFn: () => auditApi.getEntries(params),
    staleTime: 10_000,
  });
}

export function useExecutionAudit(executionId: string) {
  return useQuery({
    queryKey: queryKeys.audit.executionAudit(executionId),
    queryFn: () => auditApi.getExecutionAudit(executionId),
    enabled: !!executionId,
    staleTime: 5_000,
  });
}

export function useAuditStats() {
  return useQuery({
    queryKey: queryKeys.audit.stats,
    queryFn: () => auditApi.getStats(),
    staleTime: 30_000,
  });
}

// ============================================================
// Live trading hooks
// ============================================================

export function useAutoExecution() {
  return useQuery({
    queryKey: ["live", "auto-execution"] as const,
    queryFn: () => liveApi.getAutoExecution(),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}

export function useSetAutoExecution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { enabled?: boolean; trade_size_usdt?: number }) =>
      liveApi.setAutoExecution(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["live", "auto-execution"] });
    },
  });
}
