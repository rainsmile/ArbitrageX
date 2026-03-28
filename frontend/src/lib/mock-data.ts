import type {
  Alert,
  AnalyticsDashboard,
  ArbitrageOpportunity,
  AuditEntry,
  AuditStats,
  Balance,
  ExchangeAllocation,
  ExchangeStatus,
  ExecutionDetail,
  ExecutionLeg,
  ExecutionPlan,
  ExposureData,
  FailureAnalysis,
  InventoryFullSummary,
  InventorySummary,
  Order,
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

// ============================================================
// Helpers
// ============================================================

const now = new Date();
function ago(ms: number): string {
  return new Date(now.getTime() - ms).toISOString();
}
function future(ms: number): string {
  return new Date(now.getTime() + ms).toISOString();
}
const MIN = 60_000;
const HR = 3_600_000;
const DAY = 86_400_000;

// ============================================================
// Exchange Statuses
// ============================================================

export const mockExchanges: ExchangeStatus[] = [
  {
    exchange: "binance",
    name: "Binance",
    connected: true,
    latencyMs: 23,
    rateLimitRemaining: 1180,
    rateLimitTotal: 1200,
    lastHeartbeat: ago(2_000),
    status: "healthy",
    features: ["spot", "futures", "margin", "websocket"],
  },
  {
    exchange: "okx",
    name: "OKX",
    connected: true,
    latencyMs: 47,
    rateLimitRemaining: 580,
    rateLimitTotal: 600,
    lastHeartbeat: ago(3_000),
    status: "healthy",
    features: ["spot", "futures", "options", "websocket"],
  },
  {
    exchange: "bybit",
    name: "Bybit",
    connected: true,
    latencyMs: 61,
    rateLimitRemaining: 112,
    rateLimitTotal: 120,
    lastHeartbeat: ago(5_000),
    status: "healthy",
    features: ["spot", "futures", "websocket"],
  },
  {
    exchange: "kraken",
    name: "Kraken",
    connected: true,
    latencyMs: 55,
    rateLimitRemaining: 290,
    rateLimitTotal: 300,
    lastHeartbeat: ago(3_000),
    status: "healthy",
    features: ["spot", "margin", "websocket"],
  },
  {
    exchange: "kucoin",
    name: "KuCoin",
    connected: true,
    latencyMs: 68,
    rateLimitRemaining: 180,
    rateLimitTotal: 200,
    lastHeartbeat: ago(4_000),
    status: "healthy",
    features: ["spot", "futures", "websocket"],
  },
  {
    exchange: "gate",
    name: "Gate.io",
    connected: true,
    latencyMs: 72,
    rateLimitRemaining: 230,
    rateLimitTotal: 250,
    lastHeartbeat: ago(3_500),
    status: "healthy",
    features: ["spot", "futures", "websocket"],
  },
  {
    exchange: "htx",
    name: "HTX",
    connected: true,
    latencyMs: 59,
    rateLimitRemaining: 190,
    rateLimitTotal: 200,
    lastHeartbeat: ago(4_000),
    status: "healthy",
    features: ["spot", "futures", "websocket"],
  },
  {
    exchange: "bitget",
    name: "Bitget",
    connected: true,
    latencyMs: 65,
    rateLimitRemaining: 170,
    rateLimitTotal: 200,
    lastHeartbeat: ago(3_000),
    status: "healthy",
    features: ["spot", "futures", "websocket"],
  },
  {
    exchange: "mexc",
    name: "MEXC",
    connected: true,
    latencyMs: 78,
    rateLimitRemaining: 140,
    rateLimitTotal: 150,
    lastHeartbeat: ago(4_500),
    status: "healthy",
    features: ["spot", "futures", "websocket"],
  },
];

// ============================================================
// System Health & Metrics
// ============================================================

export const mockSystemHealth: SystemHealth = {
  status: "healthy",
  uptime: 4 * DAY + 7 * HR + 23 * MIN,
  version: "1.4.2",
  exchanges: mockExchanges,
  activeStrategies: 3,
  activeExecutions: 1,
  lastOpportunity: ago(4_200),
  lastExecution: ago(18_000),
  memoryUsageMb: 482,
  cpuUsagePercent: 12.4,
  timestamp: now.toISOString(),
};

export const mockSystemMetrics: SystemMetrics = {
  opportunitiesDetected: 1847,
  opportunitiesExecuted: 312,
  executionSuccessRate: 94.2,
  avgLatencyMs: 34,
  totalVolume24h: 2_847_312.56,
  totalPnl24h: 4_218.73,
  activeConnections: 6,
  messagesPerSecond: 342,
  ordersPerMinute: 8.4,
  timestamp: now.toISOString(),
};

// ============================================================
// Tickers
// ============================================================

export const mockTickers: Ticker[] = [
  // BTC/USDT
  { symbol: "BTC/USDT", exchange: "binance", bid: 67842.30, ask: 67843.10, bidSize: 2.341, askSize: 1.872, last: 67842.70, volume24h: 1_423_847_291, change24h: 1247.30, changePercent24h: 1.87, high24h: 68210.00, low24h: 66412.50, timestamp: ago(800) },
  { symbol: "BTC/USDT", exchange: "okx", bid: 67839.50, ask: 67841.20, bidSize: 3.102, askSize: 2.541, last: 67840.10, volume24h: 987_234_112, change24h: 1244.50, changePercent24h: 1.87, high24h: 68205.00, low24h: 66408.30, timestamp: ago(1_200) },
  { symbol: "BTC/USDT", exchange: "bybit", bid: 67844.80, ask: 67846.50, bidSize: 1.723, askSize: 1.412, last: 67845.20, volume24h: 734_912_483, change24h: 1250.10, changePercent24h: 1.88, high24h: 68215.50, low24h: 66420.00, timestamp: ago(900) },
  // ETH/USDT
  { symbol: "ETH/USDT", exchange: "binance", bid: 3542.18, ask: 3542.42, bidSize: 42.31, askSize: 38.72, last: 3542.30, volume24h: 847_291_342, change24h: 48.72, changePercent24h: 1.39, high24h: 3580.00, low24h: 3487.50, timestamp: ago(700) },
  { symbol: "ETH/USDT", exchange: "okx", bid: 3541.50, ask: 3541.88, bidSize: 51.20, askSize: 44.10, last: 3541.70, volume24h: 612_384_921, change24h: 48.10, changePercent24h: 1.38, high24h: 3578.40, low24h: 3486.20, timestamp: ago(1_100) },
  { symbol: "ETH/USDT", exchange: "bybit", bid: 3542.80, ask: 3543.30, bidSize: 33.84, askSize: 29.12, last: 3543.05, volume24h: 423_182_741, change24h: 49.45, changePercent24h: 1.42, high24h: 3581.20, low24h: 3488.90, timestamp: ago(1_000) },
  // SOL/USDT
  { symbol: "SOL/USDT", exchange: "binance", bid: 147.82, ask: 147.86, bidSize: 312.4, askSize: 287.1, last: 147.84, volume24h: 312_847_291, change24h: 4.32, changePercent24h: 3.01, high24h: 149.50, low24h: 142.80, timestamp: ago(600) },
  { symbol: "SOL/USDT", exchange: "okx", bid: 147.74, ask: 147.80, bidSize: 421.3, askSize: 398.7, last: 147.77, volume24h: 234_129_847, change24h: 4.25, changePercent24h: 2.96, high24h: 149.40, low24h: 142.70, timestamp: ago(1_300) },
  { symbol: "SOL/USDT", exchange: "bybit", bid: 147.88, ask: 147.94, bidSize: 198.2, askSize: 176.3, last: 147.91, volume24h: 178_291_423, change24h: 4.39, changePercent24h: 3.06, high24h: 149.60, low24h: 142.90, timestamp: ago(800) },
  // ARB/USDT
  { symbol: "ARB/USDT", exchange: "binance", bid: 1.1423, ask: 1.1428, bidSize: 24310, askSize: 19840, last: 1.1425, volume24h: 87_291_342, change24h: 0.0312, changePercent24h: 2.81, high24h: 1.1580, low24h: 1.1050, timestamp: ago(500) },
  { symbol: "ARB/USDT", exchange: "okx", bid: 1.1410, ask: 1.1418, bidSize: 31200, askSize: 27800, last: 1.1414, volume24h: 62_847_123, change24h: 0.0298, changePercent24h: 2.68, high24h: 1.1570, low24h: 1.1045, timestamp: ago(1_400) },
  // DOGE/USDT
  { symbol: "DOGE/USDT", exchange: "binance", bid: 0.1632, ask: 0.1633, bidSize: 482910, askSize: 391200, last: 0.1632, volume24h: 423_192_847, change24h: 0.0048, changePercent24h: 3.03, high24h: 0.1661, low24h: 0.1578, timestamp: ago(400) },
  { symbol: "DOGE/USDT", exchange: "bybit", bid: 0.1634, ask: 0.1636, bidSize: 312400, askSize: 278100, last: 0.1635, volume24h: 198_472_312, change24h: 0.0051, changePercent24h: 3.22, high24h: 0.1663, low24h: 0.1580, timestamp: ago(700) },
];

// ============================================================
// Spreads
// ============================================================

export const mockSpreads: SpreadInfo[] = [
  { symbol: "BTC/USDT", exchangeA: "binance", exchangeB: "bybit", bidA: 67842.30, askA: 67843.10, bidB: 67844.80, askB: 67846.50, spreadAB: -1.70, spreadBA: 3.40, spreadAbsAB: 1.70, spreadAbsBA: 3.40, spreadPercentAB: -0.0025, spreadPercentBA: 0.0050, timestamp: ago(800) },
  { symbol: "ETH/USDT", exchangeA: "okx", exchangeB: "bybit", bidA: 3541.50, askA: 3541.88, bidB: 3542.80, askB: 3543.30, spreadAB: -0.92, spreadBA: 1.42, spreadAbsAB: 0.92, spreadAbsBA: 1.42, spreadPercentAB: -0.026, spreadPercentBA: 0.040, timestamp: ago(700) },
  { symbol: "SOL/USDT", exchangeA: "okx", exchangeB: "bybit", bidA: 147.74, askA: 147.80, bidB: 147.88, askB: 147.94, spreadAB: -0.08, spreadBA: 0.14, spreadAbsAB: 0.08, spreadAbsBA: 0.14, spreadPercentAB: -0.054, spreadPercentBA: 0.095, timestamp: ago(900) },
  { symbol: "SOL/USDT", exchangeA: "binance", exchangeB: "okx", bidA: 147.82, askA: 147.86, bidB: 147.74, askB: 147.80, spreadAB: 0.02, spreadBA: -0.06, spreadAbsAB: 0.02, spreadAbsBA: 0.06, spreadPercentAB: 0.014, spreadPercentBA: -0.041, timestamp: ago(600) },
  { symbol: "ARB/USDT", exchangeA: "binance", exchangeB: "okx", bidA: 1.1423, askA: 1.1428, bidB: 1.1410, askB: 1.1418, spreadAB: 0.0005, spreadBA: -0.0013, spreadAbsAB: 0.0005, spreadAbsBA: 0.0013, spreadPercentAB: 0.044, spreadPercentBA: -0.114, timestamp: ago(500) },
];

// ============================================================
// Arbitrage Opportunities
// ============================================================

export const mockOpportunities: ArbitrageOpportunity[] = [
  {
    id: "opp-a1b2c3d4",
    type: "spatial",
    symbol: "BTC/USDT",
    buyExchange: "okx",
    sellExchange: "bybit",
    buyPrice: 67841.20,
    sellPrice: 67844.80,
    spreadPercent: 0.0053,
    spreadAbsolute: 3.60,
    estimatedProfit: 18.00,
    estimatedProfitPercent: 0.0053,
    maxVolume: 5.0,
    fees: 6.78,
    netProfit: 11.22,
    netProfitPercent: 0.0033,
    confidence: 0.87,
    ttl: 4500,
    detectedAt: ago(2_100),
    expiresAt: future(2_400),
  },
  {
    id: "opp-e5f6g7h8",
    type: "spatial",
    symbol: "SOL/USDT",
    buyExchange: "okx",
    sellExchange: "bybit",
    buyPrice: 147.80,
    sellPrice: 147.88,
    spreadPercent: 0.054,
    spreadAbsolute: 0.08,
    estimatedProfit: 24.00,
    estimatedProfitPercent: 0.054,
    maxVolume: 300,
    fees: 8.87,
    netProfit: 15.13,
    netProfitPercent: 0.034,
    confidence: 0.79,
    ttl: 3200,
    detectedAt: ago(1_800),
    expiresAt: future(1_400),
  },
  {
    id: "opp-i9j0k1l2",
    type: "triangular",
    symbol: "ETH/BTC",
    buyExchange: "binance",
    sellExchange: "binance",
    buyPrice: 0.05222,
    sellPrice: 0.05228,
    spreadPercent: 0.115,
    spreadAbsolute: 0.00006,
    estimatedProfit: 42.18,
    estimatedProfitPercent: 0.115,
    maxVolume: 10.0,
    fees: 14.23,
    netProfit: 27.95,
    netProfitPercent: 0.076,
    confidence: 0.92,
    ttl: 2800,
    detectedAt: ago(900),
    expiresAt: future(1_900),
  },
  {
    id: "opp-m3n4o5p6",
    type: "spatial",
    symbol: "ARB/USDT",
    buyExchange: "okx",
    sellExchange: "binance",
    buyPrice: 1.1418,
    sellPrice: 1.1423,
    spreadPercent: 0.044,
    spreadAbsolute: 0.0005,
    estimatedProfit: 12.50,
    estimatedProfitPercent: 0.044,
    maxVolume: 25000,
    fees: 5.71,
    netProfit: 6.79,
    netProfitPercent: 0.024,
    confidence: 0.71,
    ttl: 2100,
    detectedAt: ago(600),
    expiresAt: future(1_500),
  },
  {
    id: "opp-q7r8s9t0",
    type: "statistical",
    symbol: "DOGE/USDT",
    buyExchange: "binance",
    sellExchange: "bybit",
    buyPrice: 0.1633,
    sellPrice: 0.1634,
    spreadPercent: 0.061,
    spreadAbsolute: 0.0001,
    estimatedProfit: 4.82,
    estimatedProfitPercent: 0.061,
    maxVolume: 48000,
    fees: 1.57,
    netProfit: 3.25,
    netProfitPercent: 0.041,
    confidence: 0.64,
    ttl: 1800,
    detectedAt: ago(300),
    expiresAt: future(1_500),
  },
  {
    id: "opp-u1v2w3x4",
    type: "funding_rate",
    symbol: "ETH/USDT",
    buyExchange: "okx",
    sellExchange: "binance",
    buyPrice: 3541.88,
    sellPrice: 3542.18,
    spreadPercent: 0.008,
    spreadAbsolute: 0.30,
    estimatedProfit: 31.50,
    estimatedProfitPercent: 0.089,
    maxVolume: 10.0,
    fees: 7.08,
    netProfit: 24.42,
    netProfitPercent: 0.069,
    confidence: 0.83,
    ttl: 5400,
    detectedAt: ago(150),
    expiresAt: future(5_250),
  },
];

// ============================================================
// Execution Plans
// ============================================================

const completedLegs: ExecutionLeg[] = [
  { id: "leg-001a", exchange: "okx", symbol: "BTC/USDT", side: "buy", price: 67841.20, quantity: 0.15, filled: 0.15, cost: 10176.18, fee: 5.09, status: "filled", orderId: "ord-001a", executedAt: ago(42 * MIN), latencyMs: 28 },
  { id: "leg-001b", exchange: "bybit", symbol: "BTC/USDT", side: "sell", price: 67844.80, quantity: 0.15, filled: 0.15, cost: 10176.72, fee: 5.09, status: "filled", orderId: "ord-001b", executedAt: ago(42 * MIN - 340), latencyMs: 45 },
];

export const mockExecutions: ExecutionPlan[] = [
  {
    id: "exec-001",
    opportunityId: "opp-hist-001",
    strategyId: "strat-spatial-01",
    strategyType: "spatial",
    symbol: "BTC/USDT",
    status: "completed",
    legs: completedLegs,
    expectedProfit: 11.22,
    actualProfit: 10.54,
    expectedProfitPercent: 0.0033,
    actualProfitPercent: 0.0031,
    slippage: 0.0002,
    totalFees: 10.18,
    totalVolume: 20352.90,
    startedAt: ago(42 * MIN),
    completedAt: ago(42 * MIN - 500),
    duration: 500,
    error: null,
  },
  {
    id: "exec-002",
    opportunityId: "opp-hist-002",
    strategyId: "strat-triangular-01",
    strategyType: "triangular",
    symbol: "ETH/BTC",
    status: "completed",
    legs: [
      { id: "leg-002a", exchange: "binance", symbol: "ETH/USDT", side: "buy", price: 3538.42, quantity: 2.8, filled: 2.8, cost: 9907.58, fee: 4.95, status: "filled", orderId: "ord-002a", executedAt: ago(2.1 * HR), latencyMs: 22 },
      { id: "leg-002b", exchange: "binance", symbol: "ETH/BTC", side: "sell", price: 0.05224, quantity: 2.8, filled: 2.8, cost: 0.14627, fee: 0.000073, status: "filled", orderId: "ord-002b", executedAt: ago(2.1 * HR - 180), latencyMs: 19 },
      { id: "leg-002c", exchange: "binance", symbol: "BTC/USDT", side: "sell", price: 67810.50, quantity: 0.14627, filled: 0.14627, cost: 9918.12, fee: 4.96, status: "filled", orderId: "ord-002c", executedAt: ago(2.1 * HR - 400), latencyMs: 21 },
    ],
    expectedProfit: 27.95,
    actualProfit: 25.63,
    expectedProfitPercent: 0.076,
    actualProfitPercent: 0.069,
    slippage: 0.007,
    totalFees: 9.91,
    totalVolume: 29743.82,
    startedAt: ago(2.1 * HR),
    completedAt: ago(2.1 * HR - 450),
    duration: 450,
    error: null,
  },
  {
    id: "exec-003",
    opportunityId: "opp-hist-003",
    strategyId: "strat-spatial-01",
    strategyType: "spatial",
    symbol: "SOL/USDT",
    status: "failed",
    legs: [
      { id: "leg-003a", exchange: "okx", symbol: "SOL/USDT", side: "buy", price: 147.72, quantity: 100, filled: 100, cost: 14772.00, fee: 7.39, status: "filled", orderId: "ord-003a", executedAt: ago(5.4 * HR), latencyMs: 38 },
      { id: "leg-003b", exchange: "bybit", symbol: "SOL/USDT", side: "sell", price: 147.68, quantity: 100, filled: 0, cost: 0, fee: 0, status: "rejected", orderId: "ord-003b", executedAt: ago(5.4 * HR - 200), latencyMs: 312 },
    ],
    expectedProfit: 15.13,
    actualProfit: -11.39,
    expectedProfitPercent: 0.034,
    actualProfitPercent: -0.026,
    slippage: 0.06,
    totalFees: 7.39,
    totalVolume: 14772.00,
    startedAt: ago(5.4 * HR),
    completedAt: ago(5.4 * HR - 350),
    duration: 350,
    error: "Sell order rejected: insufficient liquidity on Bybit",
  },
  {
    id: "exec-004",
    opportunityId: "opp-hist-004",
    strategyId: "strat-spatial-01",
    strategyType: "spatial",
    symbol: "ETH/USDT",
    status: "completed",
    legs: [
      { id: "leg-004a", exchange: "binance", symbol: "ETH/USDT", side: "buy", price: 3540.12, quantity: 5.0, filled: 5.0, cost: 17700.60, fee: 8.85, status: "filled", orderId: "ord-004a", executedAt: ago(8.7 * HR), latencyMs: 24 },
      { id: "leg-004b", exchange: "okx", symbol: "ETH/USDT", side: "sell", price: 3541.88, quantity: 5.0, filled: 5.0, cost: 17709.40, fee: 8.85, status: "filled", orderId: "ord-004b", executedAt: ago(8.7 * HR - 280), latencyMs: 41 },
    ],
    expectedProfit: 8.80,
    actualProfit: 8.80,
    expectedProfitPercent: 0.025,
    actualProfitPercent: 0.025,
    slippage: 0.0,
    totalFees: 17.70,
    totalVolume: 35410.00,
    startedAt: ago(8.7 * HR),
    completedAt: ago(8.7 * HR - 310),
    duration: 310,
    error: null,
  },
  {
    id: "exec-005",
    opportunityId: "opp-a1b2c3d4",
    strategyId: "strat-spatial-01",
    strategyType: "spatial",
    symbol: "BTC/USDT",
    status: "executing",
    legs: [
      { id: "leg-005a", exchange: "okx", symbol: "BTC/USDT", side: "buy", price: 67841.20, quantity: 0.08, filled: 0.08, cost: 5427.30, fee: 2.71, status: "filled", orderId: "ord-005a", executedAt: ago(4_000), latencyMs: 31 },
      { id: "leg-005b", exchange: "bybit", symbol: "BTC/USDT", side: "sell", price: 67844.80, quantity: 0.08, filled: 0.0, cost: 0, fee: 0, status: "open", orderId: "ord-005b", executedAt: ago(3_700), latencyMs: 0 },
    ],
    expectedProfit: 5.98,
    actualProfit: 0,
    expectedProfitPercent: 0.0033,
    actualProfitPercent: 0,
    slippage: 0,
    totalFees: 2.71,
    totalVolume: 5427.30,
    startedAt: ago(4_000),
    completedAt: null,
    duration: 0,
    error: null,
  },
  {
    id: "exec-006",
    opportunityId: "opp-hist-006",
    strategyId: "strat-funding-01",
    strategyType: "funding_rate",
    symbol: "ETH/USDT",
    status: "completed",
    legs: [
      { id: "leg-006a", exchange: "okx", symbol: "ETH/USDT", side: "buy", price: 3535.20, quantity: 8.0, filled: 8.0, cost: 28281.60, fee: 14.14, status: "filled", orderId: "ord-006a", executedAt: ago(1.2 * DAY), latencyMs: 35 },
      { id: "leg-006b", exchange: "binance", symbol: "ETH/USDT", side: "sell", price: 3536.50, quantity: 8.0, filled: 8.0, cost: 28292.00, fee: 14.15, status: "filled", orderId: "ord-006b", executedAt: ago(1.2 * DAY - 400), latencyMs: 27 },
    ],
    expectedProfit: 10.40,
    actualProfit: 10.40,
    expectedProfitPercent: 0.037,
    actualProfitPercent: 0.037,
    slippage: 0.0,
    totalFees: 28.29,
    totalVolume: 56573.60,
    startedAt: ago(1.2 * DAY),
    completedAt: ago(1.2 * DAY - 450),
    duration: 450,
    error: null,
  },
];

// ============================================================
// Orders
// ============================================================

export const mockOrders: Order[] = mockExecutions.flatMap((exec) =>
  exec.legs.map((leg): Order => ({
    id: leg.orderId,
    executionId: exec.id,
    exchange: leg.exchange,
    symbol: leg.symbol,
    side: leg.side,
    type: "limit",
    price: leg.price,
    quantity: leg.quantity,
    filled: leg.filled,
    remaining: leg.quantity - leg.filled,
    cost: leg.cost,
    fee: leg.fee,
    status: leg.status,
    exchangeOrderId: `EX-${leg.orderId.toUpperCase()}`,
    createdAt: leg.executedAt,
    updatedAt: leg.executedAt,
    filledAt: leg.status === "filled" ? leg.executedAt : null,
  }))
);

// ============================================================
// Risk Rules
// ============================================================

export const mockRiskRules: RiskRule[] = [
  { id: "rr-001", type: "max_position_size", name: "Max Position Size", description: "Maximum size for a single position in USD equivalent", enabled: true, threshold: 50000, currentValue: 20352.90, unit: "USD", action: "block", cooldownSeconds: 0, lastTriggered: null, updatedAt: ago(2 * DAY) },
  { id: "rr-002", type: "max_daily_loss", name: "Max Daily Loss", description: "Maximum aggregate loss allowed per day", enabled: true, threshold: 500, currentValue: 11.39, unit: "USD", action: "halt", cooldownSeconds: 3600, lastTriggered: ago(5.4 * HR), updatedAt: ago(2 * DAY) },
  { id: "rr-003", type: "max_drawdown", name: "Max Drawdown", description: "Maximum drawdown from peak equity", enabled: true, threshold: 5.0, currentValue: 0.42, unit: "%", action: "halt", cooldownSeconds: 7200, lastTriggered: null, updatedAt: ago(3 * DAY) },
  { id: "rr-004", type: "max_exposure", name: "Max Total Exposure", description: "Maximum total open exposure across all exchanges", enabled: true, threshold: 200000, currentValue: 87421.30, unit: "USD", action: "reduce", cooldownSeconds: 300, lastTriggered: null, updatedAt: ago(DAY) },
  { id: "rr-005", type: "max_slippage", name: "Max Slippage", description: "Maximum allowed slippage per trade", enabled: true, threshold: 0.5, currentValue: 0.06, unit: "%", action: "warn", cooldownSeconds: 60, lastTriggered: ago(5.4 * HR), updatedAt: ago(DAY) },
  { id: "rr-006", type: "rate_limit", name: "Order Rate Limit", description: "Maximum orders per minute", enabled: true, threshold: 30, currentValue: 8.4, unit: "orders/min", action: "block", cooldownSeconds: 60, lastTriggered: null, updatedAt: ago(5 * DAY) },
  { id: "rr-007", type: "circuit_breaker", name: "Circuit Breaker", description: "Halt trading after N consecutive failures", enabled: true, threshold: 5, currentValue: 1, unit: "failures", action: "halt", cooldownSeconds: 1800, lastTriggered: null, updatedAt: ago(7 * DAY) },
  { id: "rr-008", type: "min_balance", name: "Min Exchange Balance", description: "Minimum USDT balance per exchange", enabled: true, threshold: 5000, currentValue: 12840.50, unit: "USD", action: "warn", cooldownSeconds: 300, lastTriggered: null, updatedAt: ago(4 * DAY) },
];

// ============================================================
// Risk Events
// ============================================================

export const mockRiskEvents: RiskEvent[] = [
  { id: "re-001", ruleId: "rr-005", ruleName: "Max Slippage", ruleType: "max_slippage", severity: "medium", message: "Slippage of 0.06% detected on SOL/USDT sell leg", details: { execution: "exec-003", slippage: 0.06, threshold: 0.5 }, triggered: true, action: "warn", timestamp: ago(5.4 * HR) },
  { id: "re-002", ruleId: "rr-002", ruleName: "Max Daily Loss", ruleType: "max_daily_loss", severity: "high", message: "Failed execution resulted in -$11.39 loss on SOL/USDT", details: { execution: "exec-003", loss: 11.39, dailyTotal: 11.39 }, triggered: true, action: "halt", timestamp: ago(5.4 * HR) },
  { id: "re-003", ruleId: "rr-007", ruleName: "Circuit Breaker", ruleType: "circuit_breaker", severity: "low", message: "Consecutive failure count incremented to 1", details: { count: 1, threshold: 5 }, triggered: false, action: "monitor", timestamp: ago(5.4 * HR) },
  { id: "re-004", ruleId: "rr-004", ruleName: "Max Total Exposure", ruleType: "max_exposure", severity: "low", message: "Total exposure at 43.7% of maximum", details: { current: 87421.30, threshold: 200000, percent: 43.7 }, triggered: false, action: "monitor", timestamp: ago(HR) },
];

// ============================================================
// Risk Exposure
// ============================================================

export const mockExposure: RiskExposure = {
  totalExposureUsd: 87421.30,
  maxExposureUsd: 200000,
  utilizationPercent: 43.7,
  byExchange: { binance: 38412.50, okx: 31247.80, bybit: 17761.00, kraken: 0, coinbase: 0, huobi: 0, htx: 0, gate: 0, kucoin: 0, bitget: 0, mexc: 0 },
  bySymbol: { "BTC/USDT": 42180.20, "ETH/USDT": 28410.00, "SOL/USDT": 12831.10, "ARB/USDT": 2400.00, "DOGE/USDT": 1600.00 },
  openPositions: 1,
  pendingOrders: 1,
  timestamp: now.toISOString(),
};

// ============================================================
// Balances & Inventory
// ============================================================

export const mockBalances: Balance[] = [
  // Binance
  { asset: "USDT", exchange: "binance", free: 15000, locked: 500, total: 15500, usdValue: 15500, updatedAt: ago(MIN) },
  { asset: "BTC", exchange: "binance", free: 0.30, locked: 0.0, total: 0.30, usdValue: 20340, updatedAt: ago(MIN) },
  { asset: "ETH", exchange: "binance", free: 2.0, locked: 0.0, total: 2.0, usdValue: 6914, updatedAt: ago(MIN) },
  // OKX
  { asset: "USDT", exchange: "okx", free: 10000, locked: 200, total: 10200, usdValue: 10200, updatedAt: ago(2 * MIN) },
  { asset: "ETH", exchange: "okx", free: 3.0, locked: 0.0, total: 3.0, usdValue: 10371, updatedAt: ago(2 * MIN) },
  { asset: "BTC", exchange: "okx", free: 0.20, locked: 0.0, total: 0.20, usdValue: 13560, updatedAt: ago(2 * MIN) },
  // Bybit
  { asset: "USDT", exchange: "bybit", free: 8000, locked: 0, total: 8000, usdValue: 8000, updatedAt: ago(3 * MIN) },
  { asset: "SOL", exchange: "bybit", free: 50, locked: 0, total: 50, usdValue: 7118, updatedAt: ago(3 * MIN) },
  // Kraken
  { asset: "USDT", exchange: "kraken", free: 5000, locked: 0, total: 5000, usdValue: 5000, updatedAt: ago(2 * MIN) },
  { asset: "BTC", exchange: "kraken", free: 0.15, locked: 0.0, total: 0.15, usdValue: 10170, updatedAt: ago(2 * MIN) },
  // KuCoin
  { asset: "USDT", exchange: "kucoin", free: 6000, locked: 0, total: 6000, usdValue: 6000, updatedAt: ago(3 * MIN) },
  { asset: "ETH", exchange: "kucoin", free: 2.0, locked: 0.0, total: 2.0, usdValue: 6914, updatedAt: ago(3 * MIN) },
  // Gate
  { asset: "USDT", exchange: "gate", free: 3000, locked: 0, total: 3000, usdValue: 3000, updatedAt: ago(2 * MIN) },
  { asset: "XRP", exchange: "gate", free: 5000, locked: 0, total: 5000, usdValue: 6757, updatedAt: ago(2 * MIN) },
  // HTX
  { asset: "USDT", exchange: "htx", free: 4000, locked: 0, total: 4000, usdValue: 4000, updatedAt: ago(3 * MIN) },
  { asset: "ADA", exchange: "htx", free: 15000, locked: 0, total: 15000, usdValue: 3768, updatedAt: ago(3 * MIN) },
  // Bitget
  { asset: "USDT", exchange: "bitget", free: 3500, locked: 0, total: 3500, usdValue: 3500, updatedAt: ago(2 * MIN) },
  { asset: "AVAX", exchange: "bitget", free: 300, locked: 0, total: 300, usdValue: 2675, updatedAt: ago(2 * MIN) },
  // MEXC
  { asset: "USDT", exchange: "mexc", free: 11263, locked: 0, total: 11263, usdValue: 11263, updatedAt: ago(3 * MIN) },
  { asset: "DOGE", exchange: "mexc", free: 30000, locked: 0, total: 30000, usdValue: 2819, updatedAt: ago(3 * MIN) },
];

export const mockAllocations: ExchangeAllocation[] = [
  { exchange: "binance", totalUsd: 42754, percentOfTotal: 26.3, assets: mockBalances.filter((b) => b.exchange === "binance"), status: "connected" },
  { exchange: "okx", totalUsd: 34131, percentOfTotal: 21.0, assets: mockBalances.filter((b) => b.exchange === "okx"), status: "connected" },
  { exchange: "bybit", totalUsd: 15118, percentOfTotal: 9.3, assets: mockBalances.filter((b) => b.exchange === "bybit"), status: "connected" },
  { exchange: "kraken", totalUsd: 15170, percentOfTotal: 9.3, assets: mockBalances.filter((b) => b.exchange === "kraken"), status: "connected" },
  { exchange: "kucoin", totalUsd: 12914, percentOfTotal: 7.9, assets: mockBalances.filter((b) => b.exchange === "kucoin"), status: "connected" },
  { exchange: "gate", totalUsd: 9757, percentOfTotal: 6.0, assets: mockBalances.filter((b) => b.exchange === "gate"), status: "connected" },
  { exchange: "htx", totalUsd: 7768, percentOfTotal: 4.8, assets: mockBalances.filter((b) => b.exchange === "htx"), status: "connected" },
  { exchange: "bitget", totalUsd: 6175, percentOfTotal: 3.8, assets: mockBalances.filter((b) => b.exchange === "bitget"), status: "connected" },
  { exchange: "mexc", totalUsd: 14082, percentOfTotal: 8.7, assets: mockBalances.filter((b) => b.exchange === "mexc"), status: "degraded" },
];

export const mockInventorySummary: InventorySummary = {
  totalValueUsd: 157869,
  change24h: 1823.50,
  changePercent24h: 1.17,
  exchanges: mockAllocations,
  topAssets: [
    { asset: "USDT", totalUsd: 65963, percent: 41.8 },
    { asset: "BTC", totalUsd: 44070, percent: 27.9 },
    { asset: "ETH", totalUsd: 24199, percent: 15.3 },
    { asset: "SOL", totalUsd: 7118, percent: 4.5 },
    { asset: "XRP", totalUsd: 6757, percent: 4.3 },
    { asset: "ADA", totalUsd: 3768, percent: 2.4 },
    { asset: "DOGE", totalUsd: 2819, percent: 1.8 },
    { asset: "AVAX", totalUsd: 2675, percent: 1.7 },
  ],
};

// ============================================================
// Rebalance Suggestions
// ============================================================

export const mockRebalanceSuggestions: RebalanceSuggestion[] = [
  { id: "reb-001", fromExchange: "binance", toExchange: "htx", asset: "USDT", amount: 3000, usdValue: 3000, reason: "HTX USDT balance low relative to trading activity", priority: "medium", estimatedCost: 1.50, estimatedTime: "~15 minutes" },
  { id: "reb-002", fromExchange: "okx", toExchange: "kucoin", asset: "ETH", amount: 1.5, usdValue: 5186, reason: "KuCoin ETH below optimal for cross-exchange arb", priority: "low", estimatedCost: 3.20, estimatedTime: "~20 minutes" },
  { id: "reb-003", fromExchange: "mexc", toExchange: "gate", asset: "USDT", amount: 2500, usdValue: 2500, reason: "Gate.io USDT low; MEXC has surplus for rebalancing", priority: "high", estimatedCost: 0.85, estimatedTime: "~5 minutes" },
  { id: "reb-004", fromExchange: "kraken", toExchange: "bitget", asset: "USDT", amount: 1500, usdValue: 1500, reason: "Bitget USDT low relative to recent trading volume", priority: "medium", estimatedCost: 1.20, estimatedTime: "~10 minutes" },
];

// ============================================================
// Strategies
// ============================================================

export const mockStrategies: StrategyConfig[] = [
  {
    id: "strat-spatial-01",
    name: "Cross-Exchange Spread",
    type: "spatial",
    enabled: true,
    description: "Captures price differences between exchanges for the same trading pair. Executes simultaneous buy/sell when spread exceeds threshold.",
    exchanges: ["binance", "okx", "bybit", "kraken", "kucoin", "gate", "htx", "bitget", "mexc"],
    symbols: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "POL/USDT"],
    minProfitPercent: 0.02,
    maxPositionSize: 50000,
    maxDailyTrades: 100,
    cooldownMs: 5000,
    parameters: { maxLegDelay: 500, useMarketOrders: false, limitPriceBuffer: 0.01 },
    createdAt: ago(30 * DAY),
    updatedAt: ago(2 * DAY),
    stats: { totalTrades: 847, winRate: 93.2, totalPnl: 12847.32, avgExecutionTime: 380 },
  },
  {
    id: "strat-triangular-01",
    name: "Triangular Arbitrage",
    type: "triangular",
    enabled: true,
    description: "Exploits pricing inefficiencies across three trading pairs on a single exchange (e.g. ETH/USDT -> ETH/BTC -> BTC/USDT).",
    exchanges: ["binance"],
    symbols: ["ETH/BTC", "ETH/USDT", "BTC/USDT"],
    minProfitPercent: 0.05,
    maxPositionSize: 30000,
    maxDailyTrades: 50,
    cooldownMs: 10000,
    parameters: { pathDepth: 3, minConfidence: 0.85 },
    createdAt: ago(25 * DAY),
    updatedAt: ago(5 * DAY),
    stats: { totalTrades: 234, winRate: 96.1, totalPnl: 8421.18, avgExecutionTime: 290 },
  },
  {
    id: "strat-funding-01",
    name: "Funding Rate Arb",
    type: "funding_rate",
    enabled: true,
    description: "Captures funding rate differentials between perpetual futures across exchanges.",
    exchanges: ["binance", "okx"],
    symbols: ["ETH/USDT", "BTC/USDT"],
    minProfitPercent: 0.03,
    maxPositionSize: 40000,
    maxDailyTrades: 20,
    cooldownMs: 30000,
    parameters: { minFundingDiff: 0.01, holdPeriod: "8h" },
    createdAt: ago(15 * DAY),
    updatedAt: ago(DAY),
    stats: { totalTrades: 89, winRate: 91.0, totalPnl: 3218.47, avgExecutionTime: 520 },
  },
  {
    id: "strat-stat-01",
    name: "Statistical Mean Reversion",
    type: "statistical",
    enabled: false,
    description: "Uses statistical models to identify temporary price deviations and trade the reversion to mean spread.",
    exchanges: ["binance", "bybit"],
    symbols: ["DOGE/USDT", "ARB/USDT"],
    minProfitPercent: 0.04,
    maxPositionSize: 15000,
    maxDailyTrades: 30,
    cooldownMs: 15000,
    parameters: { lookbackPeriod: "4h", zScoreThreshold: 2.0, halfLife: 120 },
    createdAt: ago(10 * DAY),
    updatedAt: ago(3 * DAY),
    stats: { totalTrades: 42, winRate: 78.6, totalPnl: 412.83, avgExecutionTime: 450 },
  },
];

// ============================================================
// Alerts
// ============================================================

export const mockAlerts: Alert[] = [
  { id: "alt-001", severity: "critical", category: "execution", title: "Execution Failed", message: "SOL/USDT sell leg rejected on Bybit due to insufficient liquidity. Buy leg already filled - position exposed.", details: { executionId: "exec-003", exchange: "bybit", symbol: "SOL/USDT" }, read: true, resolved: true, resolvedAt: ago(5 * HR), resolvedBy: "auto-hedger", createdAt: ago(5.4 * HR), updatedAt: ago(5 * HR) },
  { id: "alt-002", severity: "warning", category: "risk", title: "Daily Loss Threshold Approached", message: "Daily PnL at -$11.39, approaching max daily loss limit of $500.", details: { currentLoss: 11.39, threshold: 500, percent: 2.28 }, read: true, resolved: false, resolvedAt: null, resolvedBy: null, createdAt: ago(5.4 * HR), updatedAt: ago(5.4 * HR) },
  { id: "alt-003", severity: "warning", category: "connectivity", title: "Bybit Latency Elevated", message: "Bybit API response latency at 61ms (threshold: 50ms). May impact execution quality.", details: { exchange: "bybit", latency: 61, threshold: 50 }, read: false, resolved: false, resolvedAt: null, resolvedBy: null, createdAt: ago(32 * MIN), updatedAt: ago(32 * MIN) },
  { id: "alt-004", severity: "info", category: "opportunity", title: "High-Confidence Opportunity", message: "Triangular arbitrage on ETH/BTC detected with 92% confidence and 0.076% net profit.", details: { opportunityId: "opp-i9j0k1l2", confidence: 0.92, netProfit: 27.95 }, read: false, resolved: false, resolvedAt: null, resolvedBy: null, createdAt: ago(15 * MIN), updatedAt: ago(15 * MIN) },
  { id: "alt-005", severity: "info", category: "system", title: "Strategy Performance Update", message: "Cross-Exchange Spread strategy has completed 847 trades with 93.2% win rate and $12,847.32 total PnL.", details: { strategyId: "strat-spatial-01", winRate: 93.2, totalPnl: 12847.32 }, read: false, resolved: false, resolvedAt: null, resolvedBy: null, createdAt: ago(8 * MIN), updatedAt: ago(8 * MIN) },
  { id: "alt-006", severity: "error", category: "balance", title: "Low Balance Warning", message: "Bybit USDT free balance ($17,761) approaching minimum threshold ($5,000). Consider rebalancing.", details: { exchange: "bybit", asset: "USDT", free: 17761, threshold: 5000 }, read: false, resolved: false, resolvedAt: null, resolvedBy: null, createdAt: ago(5 * MIN), updatedAt: ago(5 * MIN) },
  { id: "alt-007", severity: "info", category: "execution", title: "Execution In Progress", message: "BTC/USDT spatial arbitrage executing: buy leg filled on OKX, sell leg pending on Bybit.", details: { executionId: "exec-005", buyExchange: "okx", sellExchange: "bybit" }, read: false, resolved: false, resolvedAt: null, resolvedBy: null, createdAt: ago(67_000), updatedAt: ago(67_000) },
];

// ============================================================
// Analytics - PnL Summary
// ============================================================

export const mockPnlSummary: PnlSummary = {
  totalPnl: 24899.80,
  totalPnlPercent: 8.29,
  totalTrades: 1212,
  winningTrades: 1128,
  losingTrades: 84,
  winRate: 93.1,
  avgProfit: 22.96,
  avgLoss: -18.42,
  maxProfit: 142.87,
  maxLoss: -87.31,
  sharpeRatio: 2.84,
  maxDrawdown: 342.18,
  maxDrawdownPercent: 1.14,
  profitFactor: 16.78,
  period: "30d",
  startDate: ago(30 * DAY),
  endDate: now.toISOString(),
};

// ============================================================
// Analytics - Profit Timeline (30 days)
// ============================================================

export const mockProfitTimeline: ProfitByPeriod[] = Array.from(
  { length: 30 },
  (_, i) => {
    const dayOffset = 29 - i;
    const basePnl = 600 + Math.sin(i * 0.4) * 200 + Math.random() * 300;
    const pnl = Number((i === 12 ? -87.31 : basePnl).toFixed(2));
    const trades = Math.floor(30 + Math.random() * 20);
    const volume = Number((80000 + Math.random() * 40000).toFixed(2));
    const fees = Number((volume * 0.001).toFixed(2));
    return {
      period: new Date(now.getTime() - dayOffset * DAY).toISOString().split("T")[0],
      pnl,
      trades,
      volume,
      fees,
      cumulativePnl: 0, // filled below
    };
  }
);
// Compute cumulative
mockProfitTimeline.reduce((acc, p) => {
  const cum = acc + p.pnl;
  p.cumulativePnl = Number(cum.toFixed(2));
  return cum;
}, 0);

// ============================================================
// Analytics - Profit by Exchange
// ============================================================

export const mockProfitByExchange: ProfitByExchange[] = [
  { exchange: "binance", pnl: 12847.32, trades: 612, volume: 1_247_312.50, fees: 1247.31, winRate: 94.1 },
  { exchange: "okx", pnl: 8421.18, trades: 389, volume: 842_118.40, fees: 842.12, winRate: 92.8 },
  { exchange: "bybit", pnl: 3631.30, trades: 211, volume: 458_312.00, fees: 458.31, winRate: 91.0 },
];

// ============================================================
// Analytics - Profit by Symbol
// ============================================================

export const mockProfitBySymbol: ProfitBySymbol[] = [
  { symbol: "BTC/USDT", pnl: 10241.82, trades: 423, volume: 987_412.30, fees: 987.41, winRate: 94.8, avgSpread: 0.0048 },
  { symbol: "ETH/USDT", pnl: 7842.31, trades: 387, volume: 724_312.80, fees: 724.31, winRate: 93.5, avgSpread: 0.0062 },
  { symbol: "ETH/BTC", pnl: 3218.47, trades: 134, volume: 412_847.20, fees: 412.85, winRate: 96.3, avgSpread: 0.0084 },
  { symbol: "SOL/USDT", pnl: 2812.40, trades: 178, volume: 312_847.10, fees: 312.85, winRate: 89.3, avgSpread: 0.0071 },
  { symbol: "ARB/USDT", pnl: 487.21, trades: 52, volume: 62_412.50, fees: 62.41, winRate: 82.7, avgSpread: 0.0092 },
  { symbol: "DOGE/USDT", pnl: 297.59, trades: 38, volume: 48_291.30, fees: 48.29, winRate: 78.9, avgSpread: 0.0055 },
];

// ============================================================
// Analytics - Profit by Strategy
// ============================================================

export const mockProfitByStrategy: ProfitByStrategy[] = [
  { strategyType: "spatial", strategyId: "strat-spatial-01", strategyName: "Cross-Exchange Spread", pnl: 12847.32, trades: 847, volume: 1_842_312.50, fees: 1842.31, winRate: 93.2 },
  { strategyType: "triangular", strategyId: "strat-triangular-01", strategyName: "Triangular Arbitrage", pnl: 8421.18, trades: 234, volume: 687_412.80, fees: 687.41, winRate: 96.1 },
  { strategyType: "funding_rate", strategyId: "strat-funding-01", strategyName: "Funding Rate Arb", pnl: 3218.47, trades: 89, volume: 412_847.20, fees: 412.85, winRate: 91.0 },
  { strategyType: "statistical", strategyId: "strat-stat-01", strategyName: "Statistical Mean Reversion", pnl: 412.83, trades: 42, volume: 62_412.50, fees: 62.41, winRate: 78.6 },
];

// ============================================================
// Analytics - Failure & Slippage
// ============================================================

export const mockFailureAnalysis: FailureAnalysis = {
  totalFailures: 84,
  byReason: [
    { reason: "Insufficient liquidity", count: 31, percent: 36.9 },
    { reason: "Order timeout", count: 22, percent: 26.2 },
    { reason: "Price moved", count: 18, percent: 21.4 },
    { reason: "Rate limit exceeded", count: 8, percent: 9.5 },
    { reason: "Network error", count: 5, percent: 6.0 },
  ],
  byExchange: [
    { exchange: "bybit", count: 38, percent: 45.2 },
    { exchange: "okx", count: 28, percent: 33.3 },
    { exchange: "binance", count: 18, percent: 21.4 },
  ],
  bySymbol: [
    { symbol: "SOL/USDT", count: 24, percent: 28.6 },
    { symbol: "ARB/USDT", count: 19, percent: 22.6 },
    { symbol: "DOGE/USDT", count: 15, percent: 17.9 },
    { symbol: "ETH/USDT", count: 14, percent: 16.7 },
    { symbol: "BTC/USDT", count: 12, percent: 14.3 },
  ],
  recentFailures: mockExecutions.filter((e) => e.status === "failed"),
};

export const mockSlippageAnalysis: SlippageAnalysis = {
  avgSlippage: 0.012,
  medianSlippage: 0.008,
  maxSlippage: 0.18,
  p95Slippage: 0.045,
  p99Slippage: 0.12,
  byExchange: [
    { exchange: "binance", avgSlippage: 0.008, count: 612 },
    { exchange: "okx", avgSlippage: 0.011, count: 389 },
    { exchange: "bybit", avgSlippage: 0.019, count: 211 },
  ],
  bySymbol: [
    { symbol: "BTC/USDT", avgSlippage: 0.006, count: 423 },
    { symbol: "ETH/USDT", avgSlippage: 0.009, count: 387 },
    { symbol: "ETH/BTC", avgSlippage: 0.007, count: 134 },
    { symbol: "SOL/USDT", avgSlippage: 0.018, count: 178 },
    { symbol: "ARB/USDT", avgSlippage: 0.024, count: 52 },
    { symbol: "DOGE/USDT", avgSlippage: 0.021, count: 38 },
  ],
  distribution: [
    { range: "0-0.005%", count: 412 },
    { range: "0.005-0.01%", count: 384 },
    { range: "0.01-0.02%", count: 247 },
    { range: "0.02-0.05%", count: 112 },
    { range: "0.05-0.1%", count: 42 },
    { range: "0.1%+", count: 15 },
  ],
};

// ============================================================
// Analytics Dashboard (aggregate)
// ============================================================

export const mockDashboard: AnalyticsDashboard = {
  summary: mockPnlSummary,
  profitTimeline: mockProfitTimeline,
  profitByExchange: mockProfitByExchange,
  profitBySymbol: mockProfitBySymbol,
  profitByStrategy: mockProfitByStrategy,
  recentExecutions: mockExecutions.slice(0, 5),
  topOpportunities: mockOpportunities.slice(0, 5),
};

// ============================================================
// WS Status
// ============================================================

export const mockWsStatus: WsStatus = {
  channels: [
    { channel: "market", connected: true, subscribers: 3, messagesPerSecond: 245, lastMessage: ago(200) },
    { channel: "opportunities", connected: true, subscribers: 2, messagesPerSecond: 12, lastMessage: ago(2_100) },
    { channel: "executions", connected: true, subscribers: 2, messagesPerSecond: 3, lastMessage: ago(4_000) },
    { channel: "alerts", connected: true, subscribers: 1, messagesPerSecond: 0.8, lastMessage: ago(5 * MIN) },
  ],
  totalConnections: 4,
  uptime: 4 * DAY + 7 * HR + 23 * MIN,
};

// ============================================================
// Phase 3: Execution Details
// ============================================================

export const mockExecutionDetails: ExecutionDetail[] = [
  {
    execution_id: "exec-p3-001",
    state: "COMPLETED",
    plan: {
      plan_id: "plan-001",
      opportunity_id: "opp-a1b2c3d4",
      strategy_type: "cross_exchange",
      mode: "paper",
      legs: [
        { leg_index: 0, exchange: "binance", symbol: "BTC/USDT", side: "BUY", order_type: "limit", planned_price: 60150.50, planned_quantity: 0.041, planned_notional: 2466.17, fee_rate: 0.001 },
        { leg_index: 1, exchange: "okx", symbol: "BTC/USDT", side: "SELL", order_type: "limit", planned_price: 60350.00, planned_quantity: 0.041, planned_notional: 2474.35, fee_rate: 0.001 },
      ],
      target_quantity: 0.041,
      target_notional_usdt: 2466.17,
      planned_gross_profit: 8.18,
      planned_net_profit: 3.26,
      planned_net_profit_pct: 0.13,
      risk_check: { approved: true, results: [{ rule_name: "max_order_value", passed: true, reason: "Order value $2,466 within limit $10,000" }], timestamp: Date.now() / 1000 - 130, violations: [] },
      simulation_result: null,
      created_at: new Date(Date.now() - 2 * MIN).toISOString(),
    },
    started_at: Date.now() / 1000 - 120,
    legs_status: { "0": "FILLED", "1": "FILLED" },
    result: {
      success: true,
      execution_id: "exec-p3-001",
      strategy_type: "cross_exchange",
      legs: [
        { leg_index: 0, exchange: "binance", symbol: "BTC/USDT", side: "BUY", planned_price: 60150.50, actual_price: 60151.20, planned_quantity: 0.041, actual_quantity: 0.041, fee: 2.47, slippage_pct: 0.001, status: "FILLED", order_id: "ord-p3-001a" },
        { leg_index: 1, exchange: "okx", symbol: "BTC/USDT", side: "SELL", planned_price: 60350.00, actual_price: 60348.80, planned_quantity: 0.041, actual_quantity: 0.041, fee: 2.47, slippage_pct: 0.002, status: "FILLED", order_id: "ord-p3-001b" },
      ],
      total_pnl_usdt: 8.10,
      total_fees_usdt: 4.94,
      net_pnl_usdt: 3.16,
      execution_time_ms: 342,
    },
    audit_trail: [
      { id: "at-001", event_type: "EXECUTION_CREATED", entity_type: "execution", entity_id: "exec-p3-001", action: "Execution plan created", details: { strategy: "CROSS_EXCHANGE" }, timestamp: Date.now() / 1000 - 125 },
      { id: "at-002", event_type: "RISK_CHECK", entity_type: "execution", entity_id: "exec-p3-001", action: "Risk check passed", details: { rules_checked: 6, violations: 0 }, timestamp: Date.now() / 1000 - 123 },
      { id: "at-003", event_type: "STATE_TRANSITION", entity_type: "execution", entity_id: "exec-p3-001", action: "CREATED -> EXECUTING", details: {}, timestamp: Date.now() / 1000 - 122 },
      { id: "at-004", event_type: "LEG_FILLED", entity_type: "leg", entity_id: "leg-0", action: "Buy leg filled on Binance", details: { price: 60151.20, quantity: 0.041 }, timestamp: Date.now() / 1000 - 120 },
      { id: "at-005", event_type: "LEG_FILLED", entity_type: "leg", entity_id: "leg-1", action: "Sell leg filled on OKX", details: { price: 60348.80, quantity: 0.041 }, timestamp: Date.now() / 1000 - 118 },
      { id: "at-006", event_type: "STATE_TRANSITION", entity_type: "execution", entity_id: "exec-p3-001", action: "EXECUTING -> COMPLETED", details: { pnl: 3.16 }, timestamp: Date.now() / 1000 - 117 },
    ],
  },
  {
    execution_id: "exec-p3-002",
    state: "EXECUTING",
    plan: {
      plan_id: "plan-002",
      opportunity_id: "opp-e5f6g7h8",
      strategy_type: "cross_exchange",
      mode: "paper",
      legs: [
        { leg_index: 0, exchange: "okx", symbol: "SOL/USDT", side: "BUY", order_type: "limit", planned_price: 147.80, planned_quantity: 50, planned_notional: 7390, fee_rate: 0.001 },
        { leg_index: 1, exchange: "bybit", symbol: "SOL/USDT", side: "SELL", order_type: "limit", planned_price: 147.88, planned_quantity: 50, planned_notional: 7394, fee_rate: 0.001 },
      ],
      target_quantity: 50,
      target_notional_usdt: 7390,
      planned_gross_profit: 4.00,
      planned_net_profit: 1.52,
      planned_net_profit_pct: 0.021,
      risk_check: { approved: true, results: [{ rule_name: "max_order_value", passed: true, reason: "Order value $7,390 within limit $10,000" }], timestamp: Date.now() / 1000 - 10, violations: [] },
      simulation_result: null,
      created_at: new Date(Date.now() - 15_000).toISOString(),
    },
    started_at: Date.now() / 1000 - 8,
    legs_status: { "0": "FILLED", "1": "PENDING" },
    result: null,
    audit_trail: [
      { id: "at-010", event_type: "EXECUTION_CREATED", entity_type: "execution", entity_id: "exec-p3-002", action: "Execution plan created", details: {}, timestamp: Date.now() / 1000 - 12 },
      { id: "at-011", event_type: "STATE_TRANSITION", entity_type: "execution", entity_id: "exec-p3-002", action: "CREATED -> EXECUTING", details: {}, timestamp: Date.now() / 1000 - 8 },
      { id: "at-012", event_type: "LEG_FILLED", entity_type: "leg", entity_id: "leg-0", action: "Buy leg filled on OKX", details: { price: 147.81, quantity: 50 }, timestamp: Date.now() / 1000 - 6 },
    ],
  },
  {
    execution_id: "exec-p3-003",
    state: "FAILED",
    plan: {
      plan_id: "plan-003",
      opportunity_id: "opp-i9j0k1l2",
      strategy_type: "triangular",
      mode: "paper",
      legs: [
        { leg_index: 0, exchange: "binance", symbol: "ETH/USDT", side: "BUY", order_type: "limit", planned_price: 3542.18, planned_quantity: 1.5, planned_notional: 5313.27, fee_rate: 0.001 },
        { leg_index: 1, exchange: "binance", symbol: "ETH/BTC", side: "SELL", order_type: "limit", planned_price: 0.05222, planned_quantity: 1.5, planned_notional: 0.07833, fee_rate: 0.001 },
        { leg_index: 2, exchange: "binance", symbol: "BTC/USDT", side: "SELL", order_type: "limit", planned_price: 67842.30, planned_quantity: 0.07833, planned_notional: 5314.50, fee_rate: 0.001 },
      ],
      target_quantity: 1.5,
      target_notional_usdt: 5313.27,
      planned_gross_profit: 1.23,
      planned_net_profit: -4.67,
      planned_net_profit_pct: -0.088,
      risk_check: { approved: true, results: [], timestamp: Date.now() / 1000 - 3700, violations: [] },
      simulation_result: null,
      created_at: new Date(Date.now() - HR).toISOString(),
    },
    started_at: Date.now() / 1000 - 3600,
    legs_status: { "0": "FILLED", "1": "FAILED", "2": "CANCELLED" },
    result: {
      success: false,
      execution_id: "exec-p3-003",
      strategy_type: "triangular",
      legs: [
        { leg_index: 0, exchange: "binance", symbol: "ETH/USDT", side: "BUY", planned_price: 3542.18, actual_price: 3542.50, planned_quantity: 1.5, actual_quantity: 1.5, fee: 5.31, slippage_pct: 0.009, status: "FILLED", order_id: "ord-p3-003a" },
        { leg_index: 1, exchange: "binance", symbol: "ETH/BTC", side: "SELL", planned_price: 0.05222, actual_price: 0, planned_quantity: 1.5, actual_quantity: 0, fee: 0, slippage_pct: 0, status: "FAILED", error: "Insufficient liquidity" },
        { leg_index: 2, exchange: "binance", symbol: "BTC/USDT", side: "SELL", planned_price: 67842.30, actual_price: 0, planned_quantity: 0.07833, actual_quantity: 0, fee: 0, slippage_pct: 0, status: "CANCELLED" },
      ],
      total_pnl_usdt: 0,
      total_fees_usdt: 5.31,
      net_pnl_usdt: -5.31,
      execution_time_ms: 1240,
      error: "Leg 1 failed: Insufficient liquidity for ETH/BTC sell",
    },
    audit_trail: [
      { id: "at-020", event_type: "EXECUTION_CREATED", entity_type: "execution", entity_id: "exec-p3-003", action: "Execution plan created", details: {}, timestamp: Date.now() / 1000 - 3650 },
      { id: "at-021", event_type: "STATE_TRANSITION", entity_type: "execution", entity_id: "exec-p3-003", action: "CREATED -> EXECUTING", details: {}, timestamp: Date.now() / 1000 - 3600 },
      { id: "at-022", event_type: "LEG_FILLED", entity_type: "leg", entity_id: "leg-0", action: "Buy leg filled", details: { price: 3542.50 }, timestamp: Date.now() / 1000 - 3598 },
      { id: "at-023", event_type: "LEG_FAILED", entity_type: "leg", entity_id: "leg-1", action: "Sell leg failed", details: { error: "Insufficient liquidity" }, timestamp: Date.now() / 1000 - 3596 },
      { id: "at-024", event_type: "STATE_TRANSITION", entity_type: "execution", entity_id: "exec-p3-003", action: "EXECUTING -> FAILED", details: { error: "Leg 1 failed" }, timestamp: Date.now() / 1000 - 3595 },
    ],
  },
];

// ============================================================
// Phase 3: Risk Decision
// ============================================================

export const mockRiskDecision: RiskDecision = {
  approved: true,
  results: [
    { rule_name: "max_order_value", passed: true, reason: "Order value $2,450 within limit $10,000" },
    { rule_name: "min_profit", passed: true, reason: "Profit 0.35% above threshold 0.05%" },
    { rule_name: "max_slippage", passed: true, reason: "Estimated slippage 0.05% within limit 0.15%" },
    { rule_name: "balance_sufficiency", passed: true, reason: "Sufficient balance on both exchanges" },
    { rule_name: "data_freshness", passed: true, reason: "Market data age 0.8s within 5s limit" },
    { rule_name: "symbol_whitelist", passed: true, reason: "BTC/USDT is on whitelist" },
  ],
  timestamp: Date.now() / 1000,
  violations: [],
};

// ============================================================
// Phase 3: Inventory Exposure
// ============================================================

export const mockInventoryExposure: ExposureData = {
  total_value_usdt: 157869,
  per_exchange: {
    binance: { value_usdt: 42754, pct_of_total: 27.1, assets: { BTC: { free: 0.30, locked: 0, usd_value: 20340 }, ETH: { free: 2.0, locked: 0, usd_value: 6914 }, USDT: { free: 15000, locked: 500, usd_value: 15500 } } },
    okx: { value_usdt: 34131, pct_of_total: 21.6, assets: { BTC: { free: 0.20, locked: 0, usd_value: 13560 }, ETH: { free: 3.0, locked: 0, usd_value: 10371 }, USDT: { free: 10000, locked: 200, usd_value: 10200 } } },
    bybit: { value_usdt: 15118, pct_of_total: 9.6, assets: { SOL: { free: 50, locked: 0, usd_value: 7118 }, USDT: { free: 8000, locked: 0, usd_value: 8000 } } },
    kraken: { value_usdt: 15170, pct_of_total: 9.6, assets: { BTC: { free: 0.15, locked: 0, usd_value: 10170 }, USDT: { free: 5000, locked: 0, usd_value: 5000 } } },
    kucoin: { value_usdt: 12914, pct_of_total: 8.2, assets: { ETH: { free: 2.0, locked: 0, usd_value: 6914 }, USDT: { free: 6000, locked: 0, usd_value: 6000 } } },
    gate: { value_usdt: 9757, pct_of_total: 6.2, assets: { XRP: { free: 5000, locked: 0, usd_value: 6757 }, USDT: { free: 3000, locked: 0, usd_value: 3000 } } },
    htx: { value_usdt: 7768, pct_of_total: 4.9, assets: { ADA: { free: 15000, locked: 0, usd_value: 3768 }, USDT: { free: 4000, locked: 0, usd_value: 4000 } } },
    bitget: { value_usdt: 6175, pct_of_total: 3.9, assets: { AVAX: { free: 300, locked: 0, usd_value: 2675 }, USDT: { free: 3500, locked: 0, usd_value: 3500 } } },
    mexc: { value_usdt: 14082, pct_of_total: 8.9, assets: { DOGE: { free: 30000, locked: 0, usd_value: 2819 }, USDT: { free: 11263, locked: 0, usd_value: 11263 } } },
  },
  per_asset: {
    BTC: { total_amount: 0.65, total_usd_value: 44070, exchanges: ["binance", "okx", "kraken"] },
    ETH: { total_amount: 7.0, total_usd_value: 24199, exchanges: ["binance", "okx", "kucoin"] },
    SOL: { total_amount: 50, total_usd_value: 7118, exchanges: ["bybit"] },
    XRP: { total_amount: 5000, total_usd_value: 6757, exchanges: ["gate"] },
    ADA: { total_amount: 15000, total_usd_value: 3768, exchanges: ["htx"] },
    AVAX: { total_amount: 300, total_usd_value: 2675, exchanges: ["bitget"] },
    DOGE: { total_amount: 30000, total_usd_value: 2819, exchanges: ["mexc"] },
    USDT: { total_amount: 65963, total_usd_value: 65963, exchanges: ["binance", "okx", "bybit", "kraken", "kucoin", "gate", "htx", "bitget", "mexc"] },
  },
  concentration_risk: 0.15,
};

// ============================================================
// Phase 3: Scanner Status
// ============================================================

export const mockScannerStatus: ScannerStatus = {
  is_running: true,
  cross_exchange: { total_scans: 14523, total_opportunities_found: 287, last_scan_at: Date.now() / 1000, last_scan_duration_ms: 12.5 },
  triangular: { total_scans: 14523, total_opportunities_found: 43, last_scan_at: Date.now() / 1000, last_scan_duration_ms: 8.3 },
};

// ============================================================
// Phase 3: Audit Entries
// ============================================================

export const mockAuditEntries: AuditEntry[] = [
  { id: "aud-001", event_type: "EXECUTION_CREATED", entity_type: "execution", entity_id: "exec-001", action: "Execution plan created", details: { strategy: "CROSS_EXCHANGE", symbol: "BTC/USDT" }, timestamp: Date.now() / 1000 - 120 },
  { id: "aud-002", event_type: "RISK_CHECK", entity_type: "execution", entity_id: "exec-001", action: "Risk check passed", details: { rules_checked: 12, violations: 0 }, timestamp: Date.now() / 1000 - 118 },
  { id: "aud-003", event_type: "STATE_TRANSITION", entity_type: "execution", entity_id: "exec-001", action: "CREATED -> RISK_CHECKING", details: {}, timestamp: Date.now() / 1000 - 117 },
  { id: "aud-004", event_type: "STATE_TRANSITION", entity_type: "execution", entity_id: "exec-001", action: "RISK_CHECKING -> READY", details: {}, timestamp: Date.now() / 1000 - 115 },
  { id: "aud-005", event_type: "STATE_TRANSITION", entity_type: "execution", entity_id: "exec-001", action: "READY -> EXECUTING", details: {}, timestamp: Date.now() / 1000 - 114 },
  { id: "aud-006", event_type: "LEG_SUBMITTED", entity_type: "leg", entity_id: "leg-001", action: "Buy leg submitted on Binance", details: { exchange: "binance", symbol: "BTC/USDT", side: "BUY" }, timestamp: Date.now() / 1000 - 113 },
  { id: "aud-007", event_type: "LEG_FILLED", entity_type: "leg", entity_id: "leg-001", action: "Buy leg filled", details: { price: 60150.5, quantity: 0.041, fee: 2.46 }, timestamp: Date.now() / 1000 - 111 },
  { id: "aud-008", event_type: "LEG_SUBMITTED", entity_type: "leg", entity_id: "leg-002", action: "Sell leg submitted on OKX", details: { exchange: "okx", symbol: "BTC/USDT", side: "SELL" }, timestamp: Date.now() / 1000 - 110 },
  { id: "aud-009", event_type: "LEG_FILLED", entity_type: "leg", entity_id: "leg-002", action: "Sell leg filled", details: { price: 60350.0, quantity: 0.041, fee: 2.47 }, timestamp: Date.now() / 1000 - 108 },
  { id: "aud-010", event_type: "STATE_TRANSITION", entity_type: "execution", entity_id: "exec-001", action: "EXECUTING -> COMPLETED", details: { pnl: 3.26 }, timestamp: Date.now() / 1000 - 107 },
];

// ============================================================
// Phase 3: Audit Stats
// ============================================================

export const mockAuditStats: AuditStats = {
  total_entries: 4872,
  by_event_type: {
    EXECUTION_CREATED: 312,
    RISK_CHECK: 312,
    STATE_TRANSITION: 1560,
    LEG_SUBMITTED: 624,
    LEG_FILLED: 598,
    LEG_FAILED: 26,
    ALERT_FIRED: 84,
    CONFIG_CHANGED: 18,
    SYSTEM_EVENT: 1338,
  },
};

// ============================================================
// Phase 3: Inventory Full Summary
// ============================================================

export const mockInventoryFullSummary: InventoryFullSummary = {
  total_value_usdt: 157869,
  exchange_count: 9,
  asset_count: 8,
  last_refresh_at: Date.now() / 1000 - 15,
  allocations: mockAllocations,
  stablecoin_balance: 65963,
};
