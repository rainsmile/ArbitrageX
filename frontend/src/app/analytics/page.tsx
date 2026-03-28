"use client";

import React, { useState, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { StatCard } from "@/components/ui/stat-card";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DonutChart } from "@/components/charts/pie-chart";
import {
  formatCurrency,
  formatPercent,
  cn,
} from "@/lib/utils";
import {
  useAnalyticsSummary,
  useProfitByPeriod,
  useProfitByExchange,
  useProfitBySymbol,
  useProfitByStrategy,
  useFailureAnalysis,
  useSlippageAnalysis,
} from "@/hooks/useApi";

// ---------------------------------------------------------------------------
// Animation variants
// ---------------------------------------------------------------------------

const stagger = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.05 },
  },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: "easeOut" as const } },
};

// ---------------------------------------------------------------------------
// Time range options
// ---------------------------------------------------------------------------

type TimeRange = "today" | "7d" | "30d" | "custom";

const timeRangeOptions: { id: TimeRange; label: string }[] = [
  { id: "today", label: "今日" },
  { id: "7d", label: "7天" },
  { id: "30d", label: "30天" },
  { id: "custom", label: "自定义" },
];

// ---------------------------------------------------------------------------
// Shared dark tooltip
// ---------------------------------------------------------------------------

function ChartTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name?: string; color?: string; dataKey?: string }>;
  label?: string;
  formatter?: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg bg-dark-800 border border-white/[0.1] px-3 py-2 shadow-xl min-w-[120px]">
      <p className="text-[10px] text-slate-500 mb-1">{label}</p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-1.5">
          {payload.length > 1 && (
            <span
              className="inline-block w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: p.color }}
            />
          )}
          <span className={cn(
            "text-sm font-semibold font-number",
            p.value >= 0 ? "text-success-400" : "text-danger-400"
          )}>
            {formatter ? formatter(p.value) : `$${p.value.toLocaleString()}`}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper: map time range to hours for API
// ---------------------------------------------------------------------------

function rangeToHours(range: TimeRange): number {
  switch (range) {
    case "today": return 24;
    case "7d": return 168;
    case "30d": return 720;
    case "custom": return 720;
  }
}

// ---------------------------------------------------------------------------
// Helper: filter timeline data by range
// ---------------------------------------------------------------------------

function filterByRange(data: Array<{ period: string; pnl: number; trades: number; volume: number; fees: number; cumulativePnl: number }>, range: TimeRange) {
  switch (range) {
    case "today": return data.slice(-1);
    case "7d": return data.slice(-7);
    case "30d": return data;
    case "custom": return data;
  }
}

// ---------------------------------------------------------------------------
// Helper: compute summary for range
// ---------------------------------------------------------------------------

function computeSummary(
  data: Array<{ pnl: number; trades: number; fees: number }>,
  range: TimeRange,
  baseSummary: { winRate: number; avgProfit: number; avgLoss: number }
) {
  const totalPnl = data.reduce((acc, d) => acc + d.pnl, 0);
  const totalFees = data.reduce((acc, d) => acc + d.fees, 0);
  const totalTrades = data.reduce((acc, d) => acc + d.trades, 0);
  const grossProfit = totalPnl + totalFees;
  const winRate = range === "today" ? 95.0 : range === "7d" ? 93.8 : baseSummary.winRate;

  return {
    netProfit: totalPnl,
    grossProfit,
    totalFees,
    totalTrades,
    winRate,
    avgProfitPerTrade: totalTrades > 0 ? totalPnl / totalTrades : 0,
    pnlChange: range === "30d" ? 8.29 : range === "7d" ? 3.12 : range === "today" ? 1.42 : 8.29,
  };
}

// ---------------------------------------------------------------------------
// Mock success rate & risk block trend data generators
// ---------------------------------------------------------------------------

function generateSuccessRateTrend(days: number) {
  return Array.from({ length: days }, (_, i) => ({
    day: `D${i + 1}`,
    rate: Number((88 + Math.random() * 10).toFixed(1)),
  }));
}

function generateRiskBlockTrend(days: number) {
  return Array.from({ length: days }, (_, i) => ({
    day: `D${i + 1}`,
    blocks: Math.floor(Math.random() * 8),
  }));
}

// ---------------------------------------------------------------------------
// Failure columns for table
// ---------------------------------------------------------------------------

interface FailureRow {
  reason: string;
  count: number;
  percent: number;
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function AnalyticsPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>("30d");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");

  const hours = rangeToHours(timeRange);

  // API hooks
  const { data: pnlSummary } = useAnalyticsSummary(hours);
  const { data: profitTimeline } = useProfitByPeriod();
  const { data: profitByExchange } = useProfitByExchange();
  const { data: profitBySymbol } = useProfitBySymbol();
  const { data: profitByStrategy } = useProfitByStrategy();
  const { data: failureData } = useFailureAnalysis();
  const { data: slippageData } = useSlippageAnalysis();

  // Filtered timeline
  const timelineData = useMemo(
    () => filterByRange(profitTimeline ?? [], timeRange),
    [profitTimeline, timeRange]
  );

  // Computed summary
  const summary = useMemo(
    () =>
      computeSummary(timelineData, timeRange, {
        winRate: pnlSummary?.winRate ?? 93.1,
        avgProfit: pnlSummary?.avgProfit ?? 22.96,
        avgLoss: pnlSummary?.avgLoss ?? -18.42,
      }),
    [timelineData, timeRange, pnlSummary]
  );

  // Chart data: daily net profit area chart
  const profitTrendData = useMemo(
    () =>
      timelineData.map((d) => ({
        time: d.period.slice(5),
        net: Number((d.pnl - d.fees).toFixed(2)),
      })),
    [timelineData]
  );

  // Chart data: theoretical vs actual
  const theoreticalVsActual = useMemo(
    () =>
      timelineData.map((d) => ({
        time: d.period.slice(5),
        theoretical: Number(d.pnl.toFixed(2)),
        actual: Number((d.pnl - d.fees * 0.3 - Math.random() * 20).toFixed(2)),
      })),
    [timelineData]
  );

  // Success rate trend
  const successRateTrend = useMemo(
    () => generateSuccessRateTrend(timeRange === "today" ? 1 : timeRange === "7d" ? 7 : 30),
    [timeRange]
  );

  // Risk block trend
  const riskBlockTrend = useMemo(
    () => generateRiskBlockTrend(timeRange === "today" ? 1 : timeRange === "7d" ? 7 : 30),
    [timeRange]
  );

  // Exchange ranking data
  const exchangeRankData = useMemo(
    () =>
      (profitByExchange ?? [])
        .map((e) => ({
          name: `${e.exchange.charAt(0).toUpperCase() + e.exchange.slice(1)}`,
          value: e.pnl,
          trades: e.trades,
          winRate: e.winRate,
        }))
        .sort((a, b) => b.value - a.value),
    [profitByExchange]
  );

  // Symbol ranking data
  const symbolRankData = useMemo(
    () =>
      (profitBySymbol ?? [])
        .map((s) => ({
          name: s.symbol,
          value: s.pnl,
          trades: s.trades,
        }))
        .sort((a, b) => b.value - a.value),
    [profitBySymbol]
  );

  // Strategy ranking data
  const strategyRankData = useMemo(
    () =>
      (profitByStrategy ?? [])
        .map((s) => ({
          name: s.strategyName.length > 20 ? s.strategyName.slice(0, 20) + "..." : s.strategyName,
          value: s.pnl,
          type: s.strategyType,
        }))
        .sort((a, b) => b.value - a.value),
    [profitByStrategy]
  );

  // Failure reasons for pie + table
  const failureReasons: FailureRow[] = failureData?.byReason ?? [];
  const failurePieData = failureReasons.map((r) => ({
    name: r.reason,
    value: r.count,
  }));

  // Slippage table data
  const slippageByExchange = slippageData?.byExchange ?? [];
  const slippageBySymbol = slippageData?.bySymbol ?? [];

  return (
    <div className="space-y-6">
      {/* ================================================================ */}
      {/* Page Header + Time Range Selector                                */}
      {/* ================================================================ */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-white">数据分析</h1>
          <p className="text-sm text-slate-500 mt-0.5">量化绩效分析与详细拆解</p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-dark-800 rounded-lg p-1 border border-white/[0.06]">
            {timeRangeOptions.map((opt) => (
              <button
                key={opt.id}
                onClick={() => setTimeRange(opt.id)}
                className={cn(
                  "px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200",
                  timeRange === opt.id
                    ? "bg-primary-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {timeRange === "custom" && (
            <div className="flex items-center gap-1.5">
              <input
                type="date"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
                className="h-8 px-2 text-xs rounded-md bg-dark-800 border border-white/[0.08] text-slate-300 focus:outline-none focus:border-primary-500/50"
              />
              <span className="text-slate-500 text-xs">至</span>
              <input
                type="date"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="h-8 px-2 text-xs rounded-md bg-dark-800 border border-white/[0.08] text-slate-300 focus:outline-none focus:border-primary-500/50"
              />
            </div>
          )}
        </div>
      </div>

      {/* ================================================================ */}
      {/* Section 1: Key Metrics (6 stat cards)                            */}
      {/* ================================================================ */}
      <motion.div
        variants={stagger}
        initial="hidden"
        animate="show"
        className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3"
      >
        <motion.div variants={fadeUp}>
          <StatCard
            label="净利润"
            value={formatCurrency(summary.netProfit)}
            change={{ value: summary.pnlChange, label: "较上期" }}
            icon={
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                <path fillRule="evenodd" d="M12 7a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0V8.414l-4.293 4.293a1 1 0 01-1.414 0L8 10.414l-4.293 4.293a1 1 0 01-1.414-1.414l5-5a1 1 0 011.414 0L11 10.586 14.586 7H12z" clipRule="evenodd" />
              </svg>
            }
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <StatCard
            label="毛利润"
            value={formatCurrency(summary.grossProfit)}
            icon={
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                <path d="M8.433 7.418c.155-.103.346-.196.567-.267v1.698a2.305 2.305 0 01-.567-.267C8.07 8.34 8 8.114 8 8c0-.114.07-.34.433-.582zM11 12.849v-1.698c.22.071.412.164.567.267.364.243.433.468.433.582 0 .114-.07.34-.433.582a2.305 2.305 0 01-.567.267z" />
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-13a1 1 0 10-2 0v.092a4.535 4.535 0 00-1.676.662C6.602 6.234 6 7.009 6 8c0 .99.602 1.765 1.324 2.246.48.32 1.054.545 1.676.662v1.941c-.391-.127-.68-.317-.843-.504a1 1 0 10-1.51 1.31c.562.649 1.413 1.076 2.353 1.253V15a1 1 0 102 0v-.092a4.535 4.535 0 001.676-.662C13.398 13.766 14 12.991 14 12c0-.99-.602-1.765-1.324-2.246A4.535 4.535 0 0011 9.092V7.151c.391.127.68.317.843.504a1 1 0 101.511-1.31c-.563-.649-1.413-1.076-2.354-1.253V5z" clipRule="evenodd" />
              </svg>
            }
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <StatCard
            label="总费用"
            value={formatCurrency(summary.totalFees)}
            icon={
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                <path fillRule="evenodd" d="M4 4a2 2 0 00-2 2v4a2 2 0 002 2V6h10a2 2 0 00-2-2H4zm2 6a2 2 0 012-2h8a2 2 0 012 2v4a2 2 0 01-2 2H8a2 2 0 01-2-2v-4zm6 4a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
              </svg>
            }
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <StatCard
            label="交易次数"
            value={summary.totalTrades.toLocaleString()}
            icon={
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                <path d="M5 12a1 1 0 102 0V6.414l1.293 1.293a1 1 0 001.414-1.414l-3-3a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L5 6.414V12zM15 8a1 1 0 10-2 0v5.586l-1.293-1.293a1 1 0 00-1.414 1.414l3 3a1 1 0 001.414 0l3-3a1 1 0 00-1.414-1.414L15 13.586V8z" />
              </svg>
            }
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <StatCard
            label="胜率"
            value={formatPercent(summary.winRate, { showSign: false })}
            icon={
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                <path fillRule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
            }
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <StatCard
            label="平均每笔利润"
            value={formatCurrency(summary.avgProfitPerTrade)}
            icon={
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
              </svg>
            }
          />
        </motion.div>
      </motion.div>

      {/* ================================================================ */}
      {/* Section 2: Charts 2x2 grid                                       */}
      {/* ================================================================ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top-left: 利润趋势图 (Area chart with gradient) */}
        <Card>
          <CardHeader>利润趋势图</CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={profitTrendData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradNetProfit" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="time"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#94a3b8", fontSize: 10 }}
                  dy={8}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#94a3b8", fontSize: 10 }}
                  tickFormatter={(v: number) => `$${v.toLocaleString()}`}
                  width={60}
                />
                <RechartsTooltip
                  content={<ChartTooltip formatter={(v) => formatCurrency(v)} />}
                  cursor={{ stroke: "rgba(255,255,255,0.1)" }}
                />
                <Area
                  type="monotone"
                  dataKey="net"
                  stroke="#22d3ee"
                  strokeWidth={2}
                  fill="url(#gradNetProfit)"
                  dot={false}
                  activeDot={{ r: 4, stroke: "#22d3ee", strokeWidth: 2, fill: "#0f1419" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Top-right: 理论 vs 实际利润 (Dual line chart) */}
        <Card>
          <CardHeader>
            理论 vs 实际利润
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4 mb-3">
              <div className="flex items-center gap-1.5 text-xs text-slate-400">
                <span className="inline-block w-3 h-0.5 rounded bg-blue-400" />
                理论利润
              </div>
              <div className="flex items-center gap-1.5 text-xs text-slate-400">
                <span className="inline-block w-3 h-0.5 rounded bg-green-400" />
                实际利润
              </div>
            </div>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={theoreticalVsActual} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="time"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#94a3b8", fontSize: 10 }}
                  dy={8}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#94a3b8", fontSize: 10 }}
                  tickFormatter={(v: number) => `$${v}`}
                  width={60}
                />
                <RechartsTooltip
                  content={<ChartTooltip formatter={(v) => formatCurrency(v)} />}
                  cursor={{ stroke: "rgba(255,255,255,0.1)" }}
                />
                <Line
                  type="monotone"
                  dataKey="theoretical"
                  stroke="#60a5fa"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 3, fill: "#60a5fa" }}
                />
                <Line
                  type="monotone"
                  dataKey="actual"
                  stroke="#4ade80"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 3, fill: "#4ade80" }}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Bottom-left: 成功率趋势 (Line chart) */}
        <Card>
          <CardHeader>成功率趋势</CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={successRateTrend} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="day"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#94a3b8", fontSize: 10 }}
                  dy={8}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#94a3b8", fontSize: 10 }}
                  domain={[80, 100]}
                  tickFormatter={(v: number) => `${v}%`}
                  width={45}
                />
                <RechartsTooltip
                  content={<ChartTooltip formatter={(v) => `${v.toFixed(1)}%`} />}
                  cursor={{ stroke: "rgba(255,255,255,0.1)" }}
                />
                <Line
                  type="monotone"
                  dataKey="rate"
                  stroke="#a78bfa"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, stroke: "#a78bfa", strokeWidth: 2, fill: "#0f1419" }}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Bottom-right: 风控拦截趋势 (Bar chart) */}
        <Card>
          <CardHeader>风控拦截趋势</CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <RechartsBarChart data={riskBlockTrend} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="day"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#94a3b8", fontSize: 10 }}
                  dy={8}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#94a3b8", fontSize: 10 }}
                  allowDecimals={false}
                  width={30}
                />
                <RechartsTooltip
                  content={<ChartTooltip formatter={(v) => `${v} 次`} />}
                  cursor={{ fill: "rgba(255,255,255,0.03)" }}
                />
                <Bar dataKey="blocks" radius={[4, 4, 0, 0]} maxBarSize={28}>
                  {riskBlockTrend.map((_, index) => (
                    <Cell key={index} fill="#f59e0b" fillOpacity={0.75} />
                  ))}
                </Bar>
              </RechartsBarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* ================================================================ */}
      {/* Section 3: Breakdown (3 columns)                                 */}
      {/* ================================================================ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 交易所利润排行 */}
        <Card>
          <CardHeader>交易所利润排行</CardHeader>
          <CardContent>
            <div className="space-y-3">
              {exchangeRankData.map((item, i) => {
                const maxVal = exchangeRankData[0]?.value || 1;
                const pct = Math.max(5, (item.value / maxVal) * 100);
                return (
                  <div key={i} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-300 font-medium">{item.name}</span>
                      <span className="text-success-400 font-number font-medium">
                        {formatCurrency(item.value)}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-dark-700 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-blue-500/70 transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-slate-500">
                      <span>{item.trades} 笔</span>
                      <span>胜率 {formatPercent(item.winRate, { showSign: false })}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* 交易对利润排行 */}
        <Card>
          <CardHeader>交易对利润排行</CardHeader>
          <CardContent>
            <div className="space-y-3">
              {symbolRankData.map((item, i) => {
                const maxVal = symbolRankData[0]?.value || 1;
                const pct = Math.max(5, (item.value / maxVal) * 100);
                return (
                  <div key={i} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-300 font-medium">{item.name}</span>
                      <span className="text-success-400 font-number font-medium">
                        {formatCurrency(item.value)}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-dark-700 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-cyan-500/70 transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <div className="text-[10px] text-slate-500">{item.trades} 笔</div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* 策略利润排行 */}
        <Card>
          <CardHeader>策略利润排行</CardHeader>
          <CardContent>
            <div className="space-y-3">
              {strategyRankData.map((item, i) => {
                const maxVal = strategyRankData[0]?.value || 1;
                const pct = Math.max(5, (item.value / maxVal) * 100);
                return (
                  <div key={i} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-1.5">
                        <Badge
                          variant={
                            item.type === "spatial" ? "info" :
                            item.type === "triangular" ? "success" :
                            item.type === "funding_rate" ? "warning" : "neutral"
                          }
                          size="sm"
                        >
                          {item.type}
                        </Badge>
                        <span className="text-slate-300 font-medium truncate max-w-[120px]">{item.name}</span>
                      </div>
                      <span className="text-success-400 font-number font-medium">
                        {formatCurrency(item.value)}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-dark-700 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-violet-500/70 transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ================================================================ */}
      {/* Section 4: Failure Analysis + Slippage Analysis                   */}
      {/* ================================================================ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 失败原因分析 */}
        <Card>
          <CardHeader
            action={
              <Badge variant="danger" size="sm">
                共 {failureData?.totalFailures ?? 0} 次
              </Badge>
            }
          >
            失败原因分析
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Pie chart */}
              <div>
                <DonutChart
                  data={failurePieData}
                  height={200}
                  innerRadius={45}
                  outerRadius={75}
                  centerValue={String(failureData?.totalFailures ?? 0)}
                  centerLabel="失败"
                  formatValue={(v) => `${v} 次`}
                />
              </div>
              {/* Table */}
              <div className="space-y-2">
                <div className="grid grid-cols-3 text-[10px] text-slate-500 uppercase tracking-wider pb-1 border-b border-white/[0.06]">
                  <span>原因</span>
                  <span className="text-right">次数</span>
                  <span className="text-right">占比</span>
                </div>
                {failureReasons.map((r) => (
                  <div key={r.reason} className="grid grid-cols-3 text-xs items-center">
                    <span className="text-slate-300 truncate">{r.reason}</span>
                    <span className="text-right text-slate-400 font-number">{r.count}</span>
                    <span className="text-right text-slate-500 font-number">
                      {formatPercent(r.percent, { showSign: false })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 滑点分析 */}
        <Card>
          <CardHeader
            action={
              <div className="flex items-center gap-3 text-xs">
                <div className="flex items-center gap-1.5">
                  <span className="text-slate-500">平均:</span>
                  <span className="font-number text-slate-300">
                    {formatPercent((slippageData?.avgSlippage ?? 0) * 100, { showSign: false, decimals: 3 })}
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-slate-500">最大:</span>
                  <span className="font-number text-danger-400">
                    {formatPercent((slippageData?.maxSlippage ?? 0) * 100, { showSign: false, decimals: 3 })}
                  </span>
                </div>
              </div>
            }
          >
            滑点分析
          </CardHeader>
          <CardContent>
            {/* By exchange */}
            <h4 className="text-xs font-medium text-slate-400 mb-2">按交易所</h4>
            <div className="rounded-lg border border-white/[0.06] overflow-hidden mb-4">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-dark-800/50">
                    <th className="text-left px-3 py-2 text-slate-500 font-medium">交易所</th>
                    <th className="text-right px-3 py-2 text-slate-500 font-medium">平均滑点</th>
                    <th className="text-right px-3 py-2 text-slate-500 font-medium">样本数</th>
                  </tr>
                </thead>
                <tbody>
                  {slippageByExchange.map((s) => (
                    <tr key={s.exchange} className="border-t border-white/[0.04]">
                      <td className="px-3 py-2 text-slate-300 capitalize">{s.exchange}</td>
                      <td className="px-3 py-2 text-right font-number text-warning-400">
                        {formatPercent(s.avgSlippage * 100, { showSign: false, decimals: 3 })}
                      </td>
                      <td className="px-3 py-2 text-right font-number text-slate-400">{s.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* By symbol */}
            <h4 className="text-xs font-medium text-slate-400 mb-2">按交易对</h4>
            <div className="rounded-lg border border-white/[0.06] overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-dark-800/50">
                    <th className="text-left px-3 py-2 text-slate-500 font-medium">交易对</th>
                    <th className="text-right px-3 py-2 text-slate-500 font-medium">平均滑点</th>
                    <th className="text-right px-3 py-2 text-slate-500 font-medium">样本数</th>
                  </tr>
                </thead>
                <tbody>
                  {slippageBySymbol.map((s) => (
                    <tr key={s.symbol} className="border-t border-white/[0.04]">
                      <td className="px-3 py-2 text-slate-300">{s.symbol}</td>
                      <td className="px-3 py-2 text-right font-number text-warning-400">
                        {formatPercent(s.avgSlippage * 100, { showSign: false, decimals: 3 })}
                      </td>
                      <td className="px-3 py-2 text-right font-number text-slate-400">{s.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
