// ============================================================
// Enums (string union types)
// ============================================================

export type ExchangeId = "binance" | "okx" | "bybit" | "kraken" | "coinbase" | "huobi" | "gate" | "kucoin";

export type OrderSide = "buy" | "sell";

export type OrderType = "market" | "limit" | "stop_limit" | "stop_market";

export type OrderStatus =
  | "pending"
  | "open"
  | "partially_filled"
  | "filled"
  | "cancelled"
  | "rejected"
  | "expired";

export type ExecutionStatus =
  | "pending"
  | "executing"
  | "partial"
  | "completed"
  | "failed"
  | "cancelled"
  | "timeout";

export type StrategyType =
  | "spatial"
  | "triangular"
  | "statistical"
  | "cross_exchange"
  | "funding_rate";

export type RiskRuleType =
  | "max_position_size"
  | "max_daily_loss"
  | "max_drawdown"
  | "max_exposure"
  | "min_balance"
  | "max_slippage"
  | "rate_limit"
  | "circuit_breaker";

export type RiskEventSeverity = "low" | "medium" | "high" | "critical";

export type AlertSeverity = "info" | "warning" | "error" | "critical";

export type AlertCategory =
  | "opportunity"
  | "execution"
  | "risk"
  | "system"
  | "balance"
  | "connectivity";

export type TradingMode = "live" | "paper" | "backtest";

export type TimeInterval = "1m" | "5m" | "15m" | "1h" | "4h" | "1d" | "7d" | "30d";

export type WsConnectionStatus = "connecting" | "connected" | "disconnected" | "reconnecting" | "error";

export type WsChannel = "market" | "opportunities" | "executions" | "alerts";

// ============================================================
// Market types
// ============================================================

export interface Ticker {
  symbol: string;
  exchange: ExchangeId;
  bid: number;
  ask: number;
  bidSize: number;
  askSize: number;
  last: number;
  volume24h: number;
  change24h: number;
  changePercent24h: number;
  high24h: number;
  low24h: number;
  timestamp: string;
}

export interface OrderbookLevel {
  price: number;
  size: number;
  total: number;
}

export interface Orderbook {
  symbol: string;
  exchange: ExchangeId;
  bids: OrderbookLevel[];
  asks: OrderbookLevel[];
  timestamp: string;
  sequenceId: number;
}

export interface SpreadInfo {
  symbol: string;
  exchangeA: ExchangeId;
  exchangeB: ExchangeId;
  bidA: number;
  askA: number;
  bidB: number;
  askB: number;
  spreadAB: number;
  spreadBA: number;
  spreadAbsAB: number;
  spreadAbsBA: number;
  spreadPercentAB: number;
  spreadPercentBA: number;
  timestamp: string;
}

// ============================================================
// Opportunity types
// ============================================================

export interface ArbitrageOpportunity {
  id: string;
  type: StrategyType;
  symbol: string;
  buyExchange: ExchangeId;
  sellExchange: ExchangeId;
  buyPrice: number;
  sellPrice: number;
  spreadPercent: number;
  spreadAbsolute: number;
  estimatedProfit: number;
  estimatedProfitPercent: number;
  maxVolume: number;
  fees: number;
  netProfit: number;
  netProfitPercent: number;
  confidence: number;
  ttl: number;
  detectedAt: string;
  expiresAt: string;
}

export interface OpportunityFilter {
  symbol?: string;
  type?: StrategyType;
  minProfit?: number;
  minProfitPercent?: number;
  exchanges?: ExchangeId[];
  limit?: number;
  offset?: number;
}

// ============================================================
// Execution types
// ============================================================

export interface ExecutionLeg {
  id: string;
  exchange: ExchangeId;
  symbol: string;
  side: OrderSide;
  price: number;
  quantity: number;
  filled: number;
  cost: number;
  fee: number;
  status: OrderStatus;
  orderId: string;
  executedAt: string;
  latencyMs: number;
}

export interface ExecutionPlan {
  id: string;
  opportunityId: string;
  strategyId: string;
  strategyType: StrategyType;
  symbol: string;
  status: ExecutionStatus;
  legs: ExecutionLeg[];
  expectedProfit: number;
  actualProfit: number;
  expectedProfitPercent: number;
  actualProfitPercent: number;
  slippage: number;
  totalFees: number;
  totalVolume: number;
  startedAt: string;
  completedAt: string | null;
  duration: number;
  error: string | null;
}

// ============================================================
// Execution Coordinator types (Phase 3)
// ============================================================

export interface ExecutionDetail {
  execution_id: string;
  state: string;
  plan: ExecutionPlanData;
  started_at: number;
  legs_status: Record<string, string>;
  result: ExecutionResult | null;
  audit_trail: AuditEntry[];
}

export interface ExecutionPlanData {
  plan_id: string;
  opportunity_id: string;
  strategy_type: StrategyType;
  mode: TradingMode;
  legs: ExecutionLegPlan[];
  target_quantity: number;
  target_notional_usdt: number;
  planned_gross_profit: number;
  planned_net_profit: number;
  planned_net_profit_pct: number;
  risk_check: RiskDecision | null;
  simulation_result: any;
  created_at: string;
}

export interface ExecutionLegPlan {
  leg_index: number;
  exchange: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  order_type: string;
  planned_price: number;
  planned_quantity: number;
  planned_notional: number;
  fee_rate: number;
}

export interface ExecutionResult {
  success: boolean;
  execution_id: string;
  strategy_type: string;
  legs: LegResult[];
  total_pnl_usdt: number;
  total_fees_usdt: number;
  net_pnl_usdt: number;
  execution_time_ms: number;
  error?: string;
}

export interface LegResult {
  leg_index: number;
  exchange: string;
  symbol: string;
  side: string;
  planned_price: number;
  actual_price: number;
  planned_quantity: number;
  actual_quantity: number;
  fee: number;
  slippage_pct: number;
  status: string;
  order_id?: string;
  error?: string;
}

// ============================================================
// Risk types (Phase 3)
// ============================================================

export interface RiskDecision {
  approved: boolean;
  results: RiskCheckResult[];
  timestamp: number;
  violations: string[];
}

export interface RiskCheckResult {
  rule_name: string;
  passed: boolean;
  reason: string;
  details?: Record<string, any>;
}

// ============================================================
// Audit types (Phase 3)
// ============================================================

export interface AuditEntry {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  action: string;
  details: Record<string, any>;
  timestamp: number;
}

export interface AuditStats {
  total_entries: number;
  by_event_type: Record<string, number>;
}

// ============================================================
// Inventory exposure types (Phase 3)
// ============================================================

export interface ExposureData {
  total_value_usdt: number;
  per_exchange: Record<string, {
    value_usdt: number;
    pct_of_total: number;
    assets: Record<string, { free: number; locked: number; usd_value: number }>;
  }>;
  per_asset: Record<string, {
    total_amount: number;
    total_usd_value: number;
    exchanges: string[];
  }>;
  concentration_risk: number;
}

export interface InventoryFullSummary {
  total_value_usdt: number;
  exchange_count: number;
  asset_count: number;
  last_refresh_at: number;
  allocations: ExchangeAllocation[];
  stablecoin_balance: number;
}

// ============================================================
// Scanner types (Phase 3)
// ============================================================

export interface ScannerStatus {
  is_running: boolean;
  cross_exchange: { total_scans: number; total_opportunities_found: number; last_scan_at: number; last_scan_duration_ms: number };
  triangular: { total_scans: number; total_opportunities_found: number; last_scan_at: number; last_scan_duration_ms: number };
}

// ============================================================
// WebSocket event types (Phase 3)
// ============================================================

export interface WsEvent {
  type: string;
  data: any;
  id: string;
  timestamp: number;
}

// ============================================================
// Order types
// ============================================================

export interface Order {
  id: string;
  executionId: string;
  exchange: ExchangeId;
  symbol: string;
  side: OrderSide;
  type: OrderType;
  price: number;
  quantity: number;
  filled: number;
  remaining: number;
  cost: number;
  fee: number;
  status: OrderStatus;
  exchangeOrderId: string;
  createdAt: string;
  updatedAt: string;
  filledAt: string | null;
}

// ============================================================
// Risk types
// ============================================================

export interface RiskRule {
  id: string;
  type: RiskRuleType;
  name: string;
  description: string;
  enabled: boolean;
  threshold: number;
  currentValue: number;
  unit: string;
  action: "warn" | "block" | "reduce" | "halt";
  cooldownSeconds: number;
  lastTriggered: string | null;
  updatedAt: string;
}

export interface RiskEvent {
  id: string;
  ruleId: string;
  ruleName: string;
  ruleType: RiskRuleType;
  severity: RiskEventSeverity;
  message: string;
  details: Record<string, unknown>;
  triggered: boolean;
  action: string;
  timestamp: string;
}

export interface RiskExposure {
  totalExposureUsd: number;
  maxExposureUsd: number;
  utilizationPercent: number;
  byExchange: Record<ExchangeId, number>;
  bySymbol: Record<string, number>;
  openPositions: number;
  pendingOrders: number;
  timestamp: string;
}

// ============================================================
// Inventory types
// ============================================================

export interface Balance {
  asset: string;
  exchange: ExchangeId;
  free: number;
  locked: number;
  total: number;
  usdValue: number;
  updatedAt: string;
}

export interface ExchangeAllocation {
  exchange: ExchangeId;
  totalUsd: number;
  percentOfTotal: number;
  assets: Balance[];
  status: "connected" | "degraded" | "disconnected";
}

export interface InventorySummary {
  totalValueUsd: number;
  change24h: number;
  changePercent24h: number;
  exchanges: ExchangeAllocation[];
  topAssets: { asset: string; totalUsd: number; percent: number }[];
}

export interface RebalanceSuggestion {
  id: string;
  fromExchange: ExchangeId;
  toExchange: ExchangeId;
  asset: string;
  amount: number;
  usdValue: number;
  reason: string;
  priority: "low" | "medium" | "high";
  estimatedCost: number;
  estimatedTime: string;
}

// ============================================================
// Analytics types
// ============================================================

export interface PnlSummary {
  totalPnl: number;
  totalPnlPercent: number;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  winRate: number;
  avgProfit: number;
  avgLoss: number;
  maxProfit: number;
  maxLoss: number;
  sharpeRatio: number;
  maxDrawdown: number;
  maxDrawdownPercent: number;
  profitFactor: number;
  period: TimeInterval;
  startDate: string;
  endDate: string;
}

export interface ProfitByPeriod {
  period: string;
  pnl: number;
  trades: number;
  volume: number;
  fees: number;
  cumulativePnl: number;
}

export interface ProfitByExchange {
  exchange: ExchangeId;
  pnl: number;
  trades: number;
  volume: number;
  fees: number;
  winRate: number;
}

export interface ProfitBySymbol {
  symbol: string;
  pnl: number;
  trades: number;
  volume: number;
  fees: number;
  winRate: number;
  avgSpread: number;
}

export interface ProfitByStrategy {
  strategyType: StrategyType;
  strategyId: string;
  strategyName: string;
  pnl: number;
  trades: number;
  volume: number;
  fees: number;
  winRate: number;
}

export interface FailureAnalysis {
  totalFailures: number;
  byReason: { reason: string; count: number; percent: number }[];
  byExchange: { exchange: ExchangeId; count: number; percent: number }[];
  bySymbol: { symbol: string; count: number; percent: number }[];
  recentFailures: ExecutionPlan[];
}

export interface SlippageAnalysis {
  avgSlippage: number;
  medianSlippage: number;
  maxSlippage: number;
  p95Slippage: number;
  p99Slippage: number;
  byExchange: { exchange: ExchangeId; avgSlippage: number; count: number }[];
  bySymbol: { symbol: string; avgSlippage: number; count: number }[];
  distribution: { range: string; count: number }[];
}

export interface AnalyticsDashboard {
  summary: PnlSummary;
  profitTimeline: ProfitByPeriod[];
  profitByExchange: ProfitByExchange[];
  profitBySymbol: ProfitBySymbol[];
  profitByStrategy: ProfitByStrategy[];
  recentExecutions: ExecutionPlan[];
  topOpportunities: ArbitrageOpportunity[];
}

// ============================================================
// Strategy types
// ============================================================

export interface StrategyConfig {
  id: string;
  name: string;
  type: StrategyType;
  enabled: boolean;
  description: string;
  exchanges: ExchangeId[];
  symbols: string[];
  minProfitPercent: number;
  maxPositionSize: number;
  maxDailyTrades: number;
  cooldownMs: number;
  parameters: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
  stats: {
    totalTrades: number;
    winRate: number;
    totalPnl: number;
    avgExecutionTime: number;
  };
}

// ============================================================
// Alert types
// ============================================================

export interface Alert {
  id: string;
  severity: AlertSeverity;
  category: AlertCategory;
  title: string;
  message: string;
  details: Record<string, unknown>;
  read: boolean;
  resolved: boolean;
  resolvedAt: string | null;
  resolvedBy: string | null;
  createdAt: string;
  updatedAt: string;
}

// ============================================================
// System types
// ============================================================

export interface ExchangeStatus {
  exchange: ExchangeId;
  name: string;
  connected: boolean;
  latencyMs: number;
  rateLimitRemaining: number;
  rateLimitTotal: number;
  lastHeartbeat: string;
  status: "healthy" | "degraded" | "down";
  features: string[];
}

export interface SystemHealth {
  status: "healthy" | "degraded" | "down";
  uptime: number;
  version: string;
  exchanges: ExchangeStatus[];
  activeStrategies: number;
  activeExecutions: number;
  lastOpportunity: string | null;
  lastExecution: string | null;
  memoryUsageMb: number;
  cpuUsagePercent: number;
  timestamp: string;
}

export interface SystemMetrics {
  opportunitiesDetected: number;
  opportunitiesExecuted: number;
  executionSuccessRate: number;
  avgLatencyMs: number;
  totalVolume24h: number;
  totalPnl24h: number;
  activeConnections: number;
  messagesPerSecond: number;
  ordersPerMinute: number;
  timestamp: string;
}

export interface WsStatus {
  channels: {
    channel: WsChannel;
    connected: boolean;
    subscribers: number;
    messagesPerSecond: number;
    lastMessage: string | null;
  }[];
  totalConnections: number;
  uptime: number;
}

// ============================================================
// API response types
// ============================================================

export interface ApiResponse<T> {
  data: T;
  success: boolean;
  message?: string;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface ApiError {
  status: number;
  message: string;
  detail?: string;
  code?: string;
}

// ============================================================
// Query parameter types
// ============================================================

export interface PaginationParams {
  page?: number;
  pageSize?: number;
}

export interface TimeRangeParams {
  startDate?: string;
  endDate?: string;
  interval?: TimeInterval;
}

export interface ExecutionFilterParams extends PaginationParams {
  status?: ExecutionStatus;
  strategy?: string;
  symbol?: string;
  exchange?: ExchangeId;
}

export interface OrderFilterParams extends PaginationParams {
  status?: OrderStatus;
  exchange?: ExchangeId;
  symbol?: string;
  side?: OrderSide;
}

export interface AlertFilterParams extends PaginationParams {
  severity?: AlertSeverity;
  category?: AlertCategory;
  read?: boolean;
  resolved?: boolean;
}

export interface AnalyticsParams extends TimeRangeParams {
  exchange?: ExchangeId;
  symbol?: string;
  strategy?: string;
}
