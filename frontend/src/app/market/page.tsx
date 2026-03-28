"use client";

import React, { useState, useMemo, useCallback, useRef } from "react";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { StatusDot } from "@/components/ui/status-dot";
import {
  formatCurrency,
  formatPercent,
  formatNumber,
  formatTimeAgo,
  cn,
} from "@/lib/utils";
import { useMarketTickers, useMarketSpreads } from "@/hooks/useApi";
import { useQueryClient } from "@tanstack/react-query";
import { useWebSocket } from "@/hooks/useWebSocket";
import type { ExchangeId, Ticker } from "@/types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STALE_THRESHOLD_MS = 30_000;

/** Top 10 hottest cryptocurrencies */
const SYMBOLS = [
  "BTC/USDT",
  "ETH/USDT",
  "SOL/USDT",
  "XRP/USDT",
  "DOGE/USDT",
  "ADA/USDT",
  "AVAX/USDT",
  "LINK/USDT",
  "DOT/USDT",
  "POL/USDT",
];

/** All monitored exchanges */
const EXCHANGES: ExchangeId[] = [
  "binance",
  "okx",
  "bybit",
  "kraken",
  "kucoin",
  "gate",
  "htx",
  "bitget",
  "mexc",
];

const EXCHANGE_LABELS: Record<string, string> = {
  binance: "Binance",
  okx: "OKX",
  bybit: "Bybit",
  kraken: "Kraken",
  kucoin: "KuCoin",
  gate: "Gate.io",
  htx: "HTX",
  bitget: "Bitget",
  mexc: "MEXC",
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ExchangeCell {
  price: number;
  volume24h: number;
  timestamp: string;
  isStale: boolean;
  isHighest: boolean;
  isLowest: boolean;
}

interface SymbolRow {
  symbol: string;
  exchanges: Record<string, ExchangeCell | null>;
  highestPrice: number;
  lowestPrice: number;
  highestExchange: string;
  lowestExchange: string;
  spreadAbsolute: number;
  spreadPercent: number;
  exchangeCount: number;
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
  if (val === 0) return "--";
  if (val >= 1000) return formatCurrency(val);
  if (val >= 1) return `$${val.toFixed(4)}`;
  return `$${val.toFixed(6)}`;
}

function fmtVolume(val: number): string {
  if (val === 0) return "--";
  return formatNumber(val, { compact: true });
}

function buildSymbolRows(tickers: Ticker[]): SymbolRow[] {
  // Group tickers: symbol -> exchange -> ticker
  const map = new Map<string, Map<string, Ticker>>();
  for (const t of tickers) {
    if (!SYMBOLS.includes(t.symbol)) continue;
    if (!map.has(t.symbol)) map.set(t.symbol, new Map());
    map.get(t.symbol)!.set(t.exchange, t);
  }

  const rows: SymbolRow[] = [];
  for (const symbol of SYMBOLS) {
    const exchangeMap = map.get(symbol);
    if (!exchangeMap) {
      rows.push({
        symbol,
        exchanges: {},
        highestPrice: 0,
        lowestPrice: 0,
        highestExchange: "",
        lowestExchange: "",
        spreadAbsolute: 0,
        spreadPercent: 0,
        exchangeCount: 0,
      });
      continue;
    }

    // Find highest & lowest prices
    let highest = -Infinity;
    let lowest = Infinity;
    let highestEx = "";
    let lowestEx = "";
    for (const [ex, t] of exchangeMap) {
      const price = t.last || (t.bid + t.ask) / 2;
      if (price > 0 && price > highest) {
        highest = price;
        highestEx = ex;
      }
      if (price > 0 && price < lowest) {
        lowest = price;
        lowestEx = ex;
      }
    }
    if (highest === -Infinity) highest = 0;
    if (lowest === Infinity) lowest = 0;

    const spreadAbs = highest - lowest;
    const spreadPct = lowest > 0 ? (spreadAbs / lowest) * 100 : 0;

    // Build exchange cells
    const exchanges: Record<string, ExchangeCell | null> = {};
    for (const ex of EXCHANGES) {
      const t = exchangeMap.get(ex);
      if (!t) {
        exchanges[ex] = null;
        continue;
      }
      const price = t.last || (t.bid + t.ask) / 2;
      const ageMs = Date.now() - new Date(t.timestamp).getTime();
      exchanges[ex] = {
        price,
        volume24h: t.volume24h,
        timestamp: t.timestamp,
        isStale: ageMs > STALE_THRESHOLD_MS,
        isHighest: ex === highestEx,
        isLowest: ex === lowestEx,
      };
    }

    rows.push({
      symbol,
      exchanges,
      highestPrice: highest,
      lowestPrice: lowest,
      highestExchange: highestEx,
      lowestExchange: lowestEx,
      spreadAbsolute: spreadAbs,
      spreadPercent: spreadPct,
      exchangeCount: exchangeMap.size,
    });
  }

  return rows;
}

function buildFreshnessData(tickers: Ticker[]): FreshnessEntry[] {
  const exchangeMap = new Map<string, { timestamps: number[]; count: number }>();
  for (const t of tickers) {
    if (!exchangeMap.has(t.exchange))
      exchangeMap.set(t.exchange, { timestamps: [], count: 0 });
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
// Component: Cross-Exchange Comparison Table
// ---------------------------------------------------------------------------

function CrossExchangeTable({ rows }: { rows: SymbolRow[] }) {
  // Find which exchanges have data
  const activeExchanges = EXCHANGES.filter((ex) =>
    rows.some((r) => r.exchanges[ex] !== null && r.exchanges[ex] !== undefined)
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-white/[0.06]">
            <th className="sticky left-0 z-10 bg-dark-900 px-4 py-3 text-left text-[11px] font-medium text-slate-500 uppercase tracking-wider whitespace-nowrap">
              币种
            </th>
            {activeExchanges.map((ex) => (
              <th
                key={ex}
                className="px-3 py-3 text-center text-[11px] font-medium text-slate-500 uppercase tracking-wider whitespace-nowrap min-w-[140px]"
              >
                {EXCHANGE_LABELS[ex] || ex}
              </th>
            ))}
            <th className="px-4 py-3 text-center text-[11px] font-medium text-slate-500 uppercase tracking-wider whitespace-nowrap min-w-[180px] border-l border-white/[0.06]">
              价差概览
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr
              key={row.symbol}
              className={cn(
                "border-b border-white/[0.03] transition-colors hover:bg-white/[0.02]",
                idx % 2 === 0 ? "bg-dark-900/30" : ""
              )}
            >
              {/* Symbol */}
              <td className="sticky left-0 z-10 bg-dark-900 px-4 py-3 whitespace-nowrap">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-slate-200">
                    {row.symbol.replace("/USDT", "")}
                  </span>
                  <span className="text-[10px] text-slate-600">/USDT</span>
                </div>
                <div className="text-[10px] text-slate-600 mt-0.5">
                  {row.exchangeCount} 个交易所
                </div>
              </td>

              {/* Exchange cells */}
              {activeExchanges.map((ex) => {
                const cell = row.exchanges[ex];
                if (!cell) {
                  return (
                    <td key={ex} className="px-3 py-3 text-center">
                      <span className="text-slate-700">--</span>
                    </td>
                  );
                }
                return (
                  <td key={ex} className="px-3 py-3">
                    <div className="flex flex-col items-center gap-1">
                      {/* Price */}
                      <span
                        className={cn(
                          "font-mono text-xs font-medium",
                          cell.isHighest
                            ? "text-emerald-400"
                            : cell.isLowest
                            ? "text-red-400"
                            : "text-slate-300"
                        )}
                      >
                        {cell.isHighest && (
                          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1 mb-0.5" />
                        )}
                        {cell.isLowest && (
                          <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-400 mr-1 mb-0.5" />
                        )}
                        {fmtPrice(cell.price)}
                      </span>
                      {/* Volume */}
                      <span className="text-[10px] text-slate-600">
                        量 {fmtVolume(cell.volume24h)}
                      </span>
                      {/* Timestamp */}
                      <span
                        className={cn(
                          "text-[10px]",
                          cell.isStale ? "text-warning-400" : "text-slate-700"
                        )}
                      >
                        {formatTimeAgo(cell.timestamp)}
                      </span>
                    </div>
                  </td>
                );
              })}

              {/* Spread overview column */}
              <td className="px-4 py-3 border-l border-white/[0.06]">
                {row.exchangeCount >= 2 ? (
                  <div className="flex flex-col items-center gap-1.5">
                    {/* Spread percent */}
                    <span
                      className={cn(
                        "font-mono text-sm font-bold",
                        row.spreadPercent > 0.1
                          ? "text-emerald-400"
                          : row.spreadPercent > 0.05
                          ? "text-yellow-400"
                          : "text-slate-400"
                      )}
                    >
                      {row.spreadPercent.toFixed(4)}%
                    </span>
                    {/* Spread absolute */}
                    <span className="font-mono text-[11px] text-slate-500">
                      {fmtPrice(row.spreadAbsolute)}
                    </span>
                    {/* Direction arrow: highest → lowest */}
                    <div className="flex items-center gap-1 text-[10px]">
                      <span className="text-emerald-400 font-medium">
                        {(EXCHANGE_LABELS[row.highestExchange] || row.highestExchange).toUpperCase()}
                      </span>
                      <span className="text-slate-600">→</span>
                      <span className="text-red-400 font-medium">
                        {(EXCHANGE_LABELS[row.lowestExchange] || row.lowestExchange).toUpperCase()}
                      </span>
                    </div>
                  </div>
                ) : (
                  <span className="text-slate-700 text-center block">--</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
                entry.status === "connected"
                  ? "正常"
                  : entry.status === "degraded"
                  ? "延迟"
                  : "离线"
              }
              size="sm"
            />
            <div>
              <span className="text-sm font-medium text-slate-200">
                {EXCHANGE_LABELS[entry.exchange] || entry.exchange.toUpperCase()}
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
                entry.status === "connected"
                  ? "text-success-400"
                  : entry.status === "degraded"
                  ? "text-warning-400"
                  : "text-danger-400"
              )}
            >
              {entry.ageMs < 1000
                ? "<1s"
                : `${(entry.ageMs / 1000).toFixed(1)}s`}
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
  const [autoRefresh, setAutoRefresh] = useState(true);
  const queryClient = useQueryClient();

  // ---- WebSocket ----
  const lastInvalidateRef = useRef(0);
  const { status: wsStatus } = useWebSocket(
    "market",
    useCallback(
      (msg) => {
        if (!autoRefresh) return;
        const now = Date.now();
        if (now - lastInvalidateRef.current < 500) return;
        lastInvalidateRef.current = now;
        queryClient.invalidateQueries({ queryKey: ["market", "tickers"] });
      },
      [autoRefresh, queryClient]
    ),
    { enabled: autoRefresh }
  );

  // Fetch all tickers (no filter — we need all exchanges × all symbols)
  const { data: tickers = [] } = useMarketTickers(undefined, undefined, {
    refetchInterval: autoRefresh ? 10_000 : false,
  });

  // Computed data
  const symbolRows = useMemo(() => buildSymbolRows(tickers), [tickers]);
  const freshnessData = useMemo(() => buildFreshnessData(tickers), [tickers]);

  const totalExchanges = freshnessData.length;
  const totalTickers = tickers.length;
  const maxSpread = symbolRows.length > 0
    ? Math.max(...symbolRows.map((r) => r.spreadPercent))
    : 0;
  const maxSpreadSymbol = symbolRows.find((r) => r.spreadPercent === maxSpread)?.symbol || "--";

  return (
    <div className="space-y-6">
      {/* ================================================================= */}
      {/* Top Bar: Title + Controls                                         */}
      {/* ================================================================= */}
      <Card padding="sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-slate-200">
              跨交易所行情对比
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              实时监控 {SYMBOLS.length} 个热门币种 × {EXCHANGES.length} 个交易所
            </p>
          </div>

          {/* Auto-refresh toggle + WS status */}
          <div className="flex items-center gap-3">
            <Switch
              checked={autoRefresh}
              onChange={setAutoRefresh}
              label="实时推送"
              size="sm"
            />
            {autoRefresh && (
              <div className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span
                    className={cn(
                      "animate-ping absolute inline-flex h-full w-full rounded-full opacity-40",
                      wsStatus === "connected"
                        ? "bg-success-400"
                        : "bg-warning-400"
                    )}
                  />
                  <span
                    className={cn(
                      "relative inline-flex rounded-full h-2 w-2",
                      wsStatus === "connected"
                        ? "bg-success-400"
                        : "bg-warning-400"
                    )}
                  />
                </span>
                <span className="text-[10px] text-slate-500">
                  {wsStatus === "connected"
                    ? "WS实时"
                    : wsStatus === "connecting"
                    ? "连接中"
                    : "轮询"}
                </span>
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* ================================================================= */}
      {/* Quick Stats Bar                                                    */}
      {/* ================================================================= */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card padding="sm">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">
            监控币种
          </div>
          <div className="text-xl font-bold text-slate-200 mt-1 font-mono">
            {SYMBOLS.length}
          </div>
        </Card>
        <Card padding="sm">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">
            接入交易所
          </div>
          <div className="text-xl font-bold text-slate-200 mt-1 font-mono">
            {totalExchanges}
          </div>
        </Card>
        <Card padding="sm">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">
            实时行情数
          </div>
          <div className="text-xl font-bold text-slate-200 mt-1 font-mono">
            {totalTickers}
          </div>
        </Card>
        <Card padding="sm">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">
            最大跨所价差
          </div>
          <div className="text-xl font-bold text-emerald-400 mt-1 font-mono">
            {maxSpread.toFixed(4)}%
          </div>
          <div className="text-[10px] text-slate-600 mt-0.5">
            {maxSpreadSymbol}
          </div>
        </Card>
      </div>

      {/* ================================================================= */}
      {/* Main Layout: Table + Sidebar                                      */}
      {/* ================================================================= */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        {/* Main: Cross-Exchange Comparison Table */}
        <div className="xl:col-span-3">
          <Card padding="none">
            <div className="px-5 pt-5 pb-3 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-slate-200">
                  行情价格对比
                </h2>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1 mb-0.5" />
                  最高价
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-400 ml-3 mr-1 mb-0.5" />
                  最低价
                </p>
              </div>
              <Badge variant="info" size="sm">
                {symbolRows.filter((r) => r.exchangeCount > 0).length} 个币种有数据
              </Badge>
            </div>
            <CrossExchangeTable rows={symbolRows} />
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Freshness Panel */}
          <Card padding="md">
            <CardHeader>数据新鲜度</CardHeader>
            <CardContent>
              <FreshnessPanel entries={freshnessData} />
            </CardContent>
          </Card>

          {/* Market Summary */}
          <Card padding="md">
            <CardHeader>市场概要</CardHeader>
            <CardContent>
              <div className="space-y-3 text-xs">
                {symbolRows
                  .filter((r) => r.exchangeCount >= 2)
                  .sort((a, b) => b.spreadPercent - a.spreadPercent)
                  .slice(0, 5)
                  .map((r) => (
                    <div
                      key={r.symbol}
                      className="flex items-center justify-between"
                    >
                      <span className="text-slate-400 font-medium">
                        {r.symbol.replace("/USDT", "")}
                      </span>
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            "font-mono",
                            r.spreadPercent > 0.1
                              ? "text-emerald-400"
                              : "text-slate-400"
                          )}
                        >
                          {r.spreadPercent.toFixed(4)}%
                        </span>
                        <span className="text-[10px] text-slate-600">
                          {r.highestExchange}→{r.lowestExchange}
                        </span>
                      </div>
                    </div>
                  ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
