"use client";

import React, { useState, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import { Tabs } from "@/components/ui/tabs";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { StatusDot } from "@/components/ui/status-dot";
import { MiniChart } from "@/components/charts/mini-chart";
import { DataTable, type Column } from "@/components/ui/data-table";
import {
  formatCurrency,
  formatPercent,
  formatNumber,
  formatTimeAgo,
  cn,
} from "@/lib/utils";
import { useMarketTickers, useMarketSpreads } from "@/hooks/useApi";
import type { ExchangeId, Ticker, SpreadInfo } from "@/types";

// ---------------------------------------------------------------------------
// Animation variants
// ---------------------------------------------------------------------------

const stagger = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: "easeOut" as const } },
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STALE_THRESHOLD_MS = 30_000;
const SPREAD_HIGHLIGHT_THRESHOLD = 0.003;

const symbolTabs = [
  { id: "all", label: "全部" },
  { id: "BTC/USDT", label: "BTC/USDT" },
  { id: "ETH/USDT", label: "ETH/USDT" },
  { id: "SOL/USDT", label: "SOL/USDT" },
  { id: "ARB/USDT", label: "ARB/USDT" },
  { id: "DOGE/USDT", label: "DOGE/USDT" },
];

const exchangeFilterTabs = [
  { id: "all", label: "全部交易所" },
  { id: "binance", label: "Binance" },
  { id: "okx", label: "OKX" },
  { id: "bybit", label: "Bybit" },
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TickerRow {
  symbol: string;
  exchange: ExchangeId;
  bid: number;
  ask: number;
  spread: number;
  spreadPercent: number;
  volume24h: number;
  timestamp: string;
  isStale: boolean;
  isBestBid: boolean;
  isBestAsk: boolean;
  [key: string]: unknown;
}

interface SpreadOverview {
  symbol: string;
  bestBidExchange: string;
  bestBidPrice: number;
  bestAskExchange: string;
  bestAskPrice: number;
  maxSpread: number;
  maxSpreadPercent: number;
  exchangeCount: number;
  sparkline: number[];
}

interface FreshnessEntry {
  exchange: string;
  latestTimestamp: string;
  ageMs: number;
  tickerCount: number;
  status: "connected" | "degraded" | "disconnected";
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPrice(val: number): string {
  if (val >= 1000) return formatCurrency(val);
  if (val >= 1) return `$${val.toFixed(4)}`;
  return `$${val.toFixed(6)}`;
}

function buildTickerRows(
  tickers: Ticker[],
  symbolFilter: string,
  exchangeFilter: string
): TickerRow[] {
  const filtered = tickers.filter((t) => {
    if (symbolFilter !== "all" && t.symbol !== symbolFilter) return false;
    if (exchangeFilter !== "all" && t.exchange !== exchangeFilter) return false;
    return true;
  });

  // Compute best bid/ask per symbol
  const bestBids = new Map<string, { price: number; exchange: string }>();
  const bestAsks = new Map<string, { price: number; exchange: string }>();
  for (const t of filtered) {
    const cur = bestBids.get(t.symbol);
    if (!cur || t.bid > cur.price) bestBids.set(t.symbol, { price: t.bid, exchange: t.exchange });
    const curAsk = bestAsks.get(t.symbol);
    if (!curAsk || t.ask < curAsk.price) bestAsks.set(t.symbol, { price: t.ask, exchange: t.exchange });
  }

  return filtered.map((t) => {
    const spread = t.ask - t.bid;
    const spreadPct = t.bid > 0 ? (spread / t.bid) * 100 : 0;
    const ageMs = Date.now() - new Date(t.timestamp).getTime();
    return {
      symbol: t.symbol,
      exchange: t.exchange,
      bid: t.bid,
      ask: t.ask,
      spread,
      spreadPercent: spreadPct,
      volume24h: t.volume24h,
      timestamp: t.timestamp,
      isStale: ageMs > STALE_THRESHOLD_MS,
      isBestBid: bestBids.get(t.symbol)?.exchange === t.exchange,
      isBestAsk: bestAsks.get(t.symbol)?.exchange === t.exchange,
    };
  }).sort((a, b) => {
    if (a.symbol !== b.symbol) return a.symbol.localeCompare(b.symbol);
    return a.exchange.localeCompare(b.exchange);
  });
}

function buildSpreadOverviews(tickers: Ticker[], symbolFilter: string): SpreadOverview[] {
  const symbolMap = new Map<string, Ticker[]>();
  for (const t of tickers) {
    if (symbolFilter !== "all" && t.symbol !== symbolFilter) continue;
    if (!symbolMap.has(t.symbol)) symbolMap.set(t.symbol, []);
    symbolMap.get(t.symbol)!.push(t);
  }

  const overviews: SpreadOverview[] = [];
  for (const [symbol, tickerList] of symbolMap) {
    let bestBid = 0, bestAsk = Infinity;
    let bestBidEx = "", bestAskEx = "";
    let bestBidPrice = 0, bestAskPrice = 0;

    for (const t of tickerList) {
      if (t.bid > bestBid) { bestBid = t.bid; bestBidEx = t.exchange; bestBidPrice = t.bid; }
      if (t.ask < bestAsk) { bestAsk = t.ask; bestAskEx = t.exchange; bestAskPrice = t.ask; }
    }

    const maxSpread = bestBid - bestAsk;
    const maxSpreadPct = bestAsk > 0 ? (maxSpread / bestAsk) * 100 : 0;

    const seed = symbol.charCodeAt(0) + symbol.charCodeAt(symbol.length - 1);
    const sparkline = Array.from({ length: 20 }, (_, i) => {
      const base = Math.abs(maxSpreadPct) * 0.8;
      return base + Math.sin((seed + i) * 0.5) * base * 0.4 + Math.random() * base * 0.2;
    });

    overviews.push({
      symbol,
      bestBidExchange: bestBidEx,
      bestBidPrice,
      bestAskExchange: bestAskEx,
      bestAskPrice,
      maxSpread,
      maxSpreadPercent: maxSpreadPct,
      exchangeCount: tickerList.length,
      sparkline,
    });
  }

  return overviews.sort((a, b) => b.maxSpreadPercent - a.maxSpreadPercent);
}

function buildFreshnessData(tickers: Ticker[]): FreshnessEntry[] {
  const exchangeMap = new Map<string, { timestamps: number[]; count: number }>();
  for (const t of tickers) {
    if (!exchangeMap.has(t.exchange)) exchangeMap.set(t.exchange, { timestamps: [], count: 0 });
    const entry = exchangeMap.get(t.exchange)!;
    entry.timestamps.push(new Date(t.timestamp).getTime());
    entry.count++;
  }

  return Array.from(exchangeMap.entries()).map(([exchange, data]) => {
    const latest = Math.max(...data.timestamps);
    const ageMs = Date.now() - latest;
    const status: "connected" | "degraded" | "disconnected" =
      ageMs < 5000 ? "connected" : ageMs < 30000 ? "degraded" : "disconnected";
    return {
      exchange,
      latestTimestamp: new Date(latest).toISOString(),
      ageMs,
      tickerCount: data.count,
      status,
    };
  });
}

// ---------------------------------------------------------------------------
// Component: Price Comparison Table
// ---------------------------------------------------------------------------

function PriceComparisonTable({
  rows,
  onRowClick,
}: {
  rows: TickerRow[];
  onRowClick?: (row: TickerRow) => void;
}) {
  const columns: Column<TickerRow & Record<string, unknown>>[] = [
    {
      key: "symbol",
      header: "交易对",
      width: "120px",
      render: (row) => (
        <span className="text-sm font-medium text-slate-200">{row.symbol}</span>
      ),
    },
    {
      key: "exchange",
      header: "交易所",
      width: "100px",
      render: (row) => (
        <Badge
          variant={
            row.exchange === "binance" ? "warning" : row.exchange === "okx" ? "info" : "neutral"
          }
          size="sm"
        >
          {(row.exchange as string).toUpperCase()}
        </Badge>
      ),
    },
    {
      key: "bid",
      header: "Bid",
      align: "right",
      render: (row) => (
        <span
          className={cn(
            "font-mono text-xs",
            row.isBestBid ? "text-success-400 font-semibold" : "text-slate-400"
          )}
        >
          {fmtPrice(row.bid as number)}
        </span>
      ),
    },
    {
      key: "ask",
      header: "Ask",
      align: "right",
      render: (row) => (
        <span
          className={cn(
            "font-mono text-xs",
            row.isBestAsk ? "text-danger-400 font-semibold" : "text-slate-400"
          )}
        >
          {fmtPrice(row.ask as number)}
        </span>
      ),
    },
    {
      key: "spread",
      header: "Spread",
      align: "right",
      sortable: true,
      render: (row) => (
        <span className="font-mono text-xs text-slate-300">
          {fmtPrice(Math.abs(row.spread as number))}
        </span>
      ),
    },
    {
      key: "spreadPercent",
      header: "Spread%",
      align: "right",
      sortable: true,
      render: (row) => {
        const pct = row.spreadPercent as number;
        return (
          <span
            className={cn(
              "font-mono text-xs font-medium",
              pct > SPREAD_HIGHLIGHT_THRESHOLD * 100 ? "text-success-300" :
              pct > 0 ? "text-success-400" : "text-slate-400"
            )}
          >
            {formatPercent(pct, { decimals: 4 })}
          </span>
        );
      },
    },
    {
      key: "volume24h",
      header: "24h量",
      align: "right",
      sortable: true,
      render: (row) => (
        <span className="font-mono text-xs text-slate-500">
          {formatNumber(row.volume24h as number, { compact: true })}
        </span>
      ),
    },
    {
      key: "timestamp",
      header: "最后更新",
      align: "right",
      width: "100px",
      render: (row) => (
        <span
          className={cn(
            "font-mono text-[11px]",
            row.isStale ? "text-warning-400" : "text-slate-600"
          )}
        >
          {row.isStale && (
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-warning-400 mr-1.5 animate-pulse" />
          )}
          {formatTimeAgo(row.timestamp as string)}
        </span>
      ),
    },
  ];

  return (
    <DataTable<TickerRow & Record<string, unknown>>
      columns={columns}
      data={rows as (TickerRow & Record<string, unknown>)[]}
      keyExtractor={(row) => `${row.exchange}-${row.symbol}`}
      onRowClick={onRowClick}
      compact
    />
  );
}

// ---------------------------------------------------------------------------
// Component: Spread Overview Cards
// ---------------------------------------------------------------------------

function SpreadOverviewCards({ overviews }: { overviews: SpreadOverview[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {overviews.map((item, idx) => (
        <motion.div
          key={item.symbol}
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: idx * 0.04, duration: 0.25 }}
        >
          <Card padding="sm" hover className="h-full">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-slate-200">{item.symbol}</span>
              <Badge
                variant={item.maxSpreadPercent > 0 ? "success" : "neutral"}
                size="sm"
              >
                {item.exchangeCount} 交易所
              </Badge>
            </div>

            {/* Best buy/sell */}
            <div className="space-y-2 text-xs mb-3">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">最优买入</span>
                <div className="flex items-center gap-2">
                  <Badge variant="success" size="sm">{item.bestAskExchange.toUpperCase()}</Badge>
                  <span className="font-mono text-slate-200">{fmtPrice(item.bestAskPrice)}</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">最优卖出</span>
                <div className="flex items-center gap-2">
                  <Badge variant="danger" size="sm">{item.bestBidExchange.toUpperCase()}</Badge>
                  <span className="font-mono text-slate-200">{fmtPrice(item.bestBidPrice)}</span>
                </div>
              </div>
            </div>

            {/* Spread stats */}
            <div className="grid grid-cols-2 gap-2 text-xs mb-3">
              <div>
                <span className="text-slate-500">跨所价差</span>
                <p className="font-mono text-slate-200 mt-0.5">
                  {fmtPrice(Math.abs(item.maxSpread))}
                </p>
              </div>
              <div>
                <span className="text-slate-500">价差%</span>
                <p
                  className={cn(
                    "font-mono mt-0.5",
                    item.maxSpreadPercent > 0 ? "text-success-400" : "text-slate-300"
                  )}
                >
                  {formatPercent(item.maxSpreadPercent, { decimals: 4 })}
                </p>
              </div>
            </div>

            {/* Sparkline */}
            <div className="flex items-center justify-center pt-2 border-t border-white/[0.04]">
              <MiniChart data={item.sparkline} width={140} height={32} color="auto" />
            </div>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component: Data Freshness Panel
// ---------------------------------------------------------------------------

function FreshnessPanel({ entries }: { entries: FreshnessEntry[] }) {
  return (
    <div className="space-y-2">
      {entries.map((entry) => (
        <div
          key={entry.exchange}
          className="flex items-center justify-between rounded-lg bg-dark-800/40 border border-white/[0.03] px-4 py-3"
        >
          <div className="flex items-center gap-3">
            <StatusDot
              status={entry.status}
              label={
                entry.status === "connected" ? "正常" :
                entry.status === "degraded" ? "延迟" : "离线"
              }
              size="sm"
            />
            <div>
              <span className="text-sm font-medium text-slate-200 capitalize">
                {entry.exchange.toUpperCase()}
              </span>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {entry.tickerCount} 个交易对
              </p>
            </div>
          </div>
          <div className="text-right">
            <span
              className={cn(
                "font-mono text-xs",
                entry.status === "connected" ? "text-success-400" :
                entry.status === "degraded" ? "text-warning-400" : "text-danger-400"
              )}
            >
              {entry.ageMs < 1000 ? "<1s" : `${(entry.ageMs / 1000).toFixed(1)}s`}
            </span>
            <p className="text-[10px] text-slate-600 mt-0.5">数据延迟</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Market Page
// ---------------------------------------------------------------------------

export default function MarketPage() {
  const [activeSymbol, setActiveSymbol] = useState("all");
  const [activeExchange, setActiveExchange] = useState("all");
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Hooks with conditional refetch
  const { data: tickers = [] } = useMarketTickers(
    activeExchange !== "all" ? activeExchange : undefined,
    activeSymbol !== "all" ? activeSymbol : undefined,
    { refetchInterval: autoRefresh ? 3_000 : false }
  );
  const { data: spreads = [] } = useMarketSpreads(
    activeSymbol !== "all" ? { symbol: activeSymbol } : undefined,
    { refetchInterval: autoRefresh ? 3_000 : false }
  );

  // Computed data
  const tickerRows = useMemo(
    () => buildTickerRows(tickers, activeSymbol, activeExchange),
    [tickers, activeSymbol, activeExchange]
  );

  const spreadOverviews = useMemo(
    () => buildSpreadOverviews(tickers, activeSymbol),
    [tickers, activeSymbol]
  );

  const freshnessData = useMemo(
    () => buildFreshnessData(tickers),
    [tickers]
  );

  const uniqueSymbols = useMemo(
    () => new Set(tickerRows.map((r) => r.symbol)).size,
    [tickerRows]
  );

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      {/* ================================================================= */}
      {/* Top Section: Filters                                              */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp}>
        <Card padding="sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-4">
              {/* Symbol filter */}
              <div>
                <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1.5">交易对</p>
                <Tabs
                  tabs={symbolTabs}
                  activeTab={activeSymbol}
                  onChange={setActiveSymbol}
                />
              </div>
              {/* Exchange filter */}
              <div>
                <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1.5">交易所</p>
                <Tabs
                  tabs={exchangeFilterTabs}
                  activeTab={activeExchange}
                  onChange={setActiveExchange}
                />
              </div>
            </div>

            {/* Auto-refresh toggle */}
            <div className="flex items-center gap-3">
              <Switch
                checked={autoRefresh}
                onChange={setAutoRefresh}
                label="自动刷新"
                size="sm"
              />
              {autoRefresh && (
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success-400 opacity-40" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-success-400" />
                </span>
              )}
            </div>
          </div>
        </Card>
      </motion.div>

      {/* ================================================================= */}
      {/* Main Layout: Table + Sidebar                                      */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp} className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        {/* Main: Price Comparison Table */}
        <div className="xl:col-span-3">
          <Card padding="none">
            <div className="px-5 pt-5 pb-0">
              <CardHeader
                action={
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-500 uppercase tracking-wider">
                      按交易对分组
                    </span>
                    <Badge variant="info" size="sm">
                      {tickerRows.length} 条记录
                    </Badge>
                    <Badge variant="neutral" size="sm">
                      {uniqueSymbols} 交易对
                    </Badge>
                  </div>
                }
              >
                行情价格对比
              </CardHeader>
            </div>
            <PriceComparisonTable rows={tickerRows} />
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Freshness Panel */}
          <Card padding="md">
            <CardHeader>
              数据新鲜度
            </CardHeader>
            <CardContent>
              <FreshnessPanel entries={freshnessData} />
            </CardContent>
          </Card>

          {/* Quick Stats */}
          <Card padding="md">
            <CardHeader>市场概要</CardHeader>
            <CardContent>
              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">监控交易对</span>
                  <span className="font-mono text-slate-200">{uniqueSymbols}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">接入交易所</span>
                  <span className="font-mono text-slate-200">{freshnessData.length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">最大跨所价差</span>
                  <span className="font-mono text-success-400">
                    {spreadOverviews.length > 0
                      ? formatPercent(spreadOverviews[0].maxSpreadPercent, { decimals: 4 })
                      : "--"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">过期数据</span>
                  <span className={cn(
                    "font-mono",
                    tickerRows.some((r) => r.isStale) ? "text-warning-400" : "text-success-400"
                  )}>
                    {tickerRows.filter((r) => r.isStale).length} 条
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">价差报告数</span>
                  <span className="font-mono text-slate-200">{spreads.length}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </motion.div>

      {/* ================================================================= */}
      {/* Spread Overview Cards                                             */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-slate-300">价差概览</h2>
          <span className="text-xs text-slate-500">
            {spreadOverviews.length} 个交易对 | 最优买卖交易所标注
          </span>
        </div>
        <SpreadOverviewCards overviews={spreadOverviews} />
      </motion.div>
    </motion.div>
  );
}
