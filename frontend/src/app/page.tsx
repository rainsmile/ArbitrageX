"use client";

import React, { useMemo } from "react";
import { motion } from "framer-motion";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { StatusDot } from "@/components/ui/status-dot";
import { MiniChart } from "@/components/charts/mini-chart";
import {
  formatCurrency,
  formatPercent,
  formatTimeAgo,
  formatDuration,
  cn,
} from "@/lib/utils";
import {
  useAnalyticsDashboard,
  useScannerStatus,
  useActiveAlerts,
  useInventorySummary,
  useExchanges,
} from "@/hooks/useApi";
import type {
  ArbitrageOpportunity,
  ExecutionPlan,
  Alert,
  ExchangeStatus,
  ProfitByExchange,
} from "@/types";

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
  hidden: { opacity: 0, y: 14 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: "easeOut" as const },
  },
};

const cardClass =
  "rounded-xl border border-white/[0.06] bg-white/[0.02] backdrop-blur-sm";

// ---------------------------------------------------------------------------
// Chart colors
// ---------------------------------------------------------------------------

const DONUT_COLORS = [
  "#3b82f6",
  "#22d3ee",
  "#4ade80",
  "#f59e0b",
  "#a78bfa",
  "#f87171",
  "#fb923c",
  "#e879f9",
];

const BAR_COLORS = ["#3b82f6", "#22d3ee", "#4ade80", "#f59e0b", "#a78bfa"];

// ---------------------------------------------------------------------------
// Custom chart tooltip
// ---------------------------------------------------------------------------

function ChartTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
  formatter?: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const val = payload[0].value;
  return (
    <div className="rounded-lg bg-dark-800 border border-white/[0.1] px-3 py-2 shadow-xl">
      <p className="text-[10px] text-slate-500 mb-0.5">{label}</p>
      <p
        className={cn(
          "text-sm font-semibold font-number",
          val >= 0 ? "text-emerald-400" : "text-red-400"
        )}
      >
        {formatter ? formatter(val) : formatCurrency(val)}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline sub-components
// ---------------------------------------------------------------------------

/** Single stat card for the top row */
function MetricCard({
  label,
  value,
  subValue,
  accent = "default",
  children,
}: {
  label: string;
  value: React.ReactNode;
  subValue?: React.ReactNode;
  accent?: "default" | "emerald" | "red" | "cyan";
  children?: React.ReactNode;
}) {
  const accentBorder =
    accent === "emerald"
      ? "hover:border-emerald-500/30"
      : accent === "red"
        ? "hover:border-red-500/30"
        : accent === "cyan"
          ? "hover:border-cyan-500/30"
          : "hover:border-white/[0.12]";

  return (
    <motion.div
      variants={fadeUp}
      className={cn(
        cardClass,
        "p-4 transition-all duration-300",
        accentBorder
      )}
    >
      <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider mb-2">
        {label}
      </p>
      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0">
          <p className="text-2xl font-bold text-white font-number truncate leading-tight">
            {value}
          </p>
          {subValue && (
            <div className="mt-1.5 text-xs text-slate-500">{subValue}</div>
          )}
        </div>
        {children && <div className="shrink-0">{children}</div>}
      </div>
    </motion.div>
  );
}

/** Single opportunity row in the live feed */
function OpportunityRow({ opp, idx }: { opp: ArbitrageOpportunity; idx: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: idx * 0.04, duration: 0.25 }}
      className="flex items-center justify-between rounded-lg bg-dark-800/40 border border-white/[0.04] px-3 py-2.5 hover:border-white/[0.1] hover:bg-dark-800/60 transition-all cursor-pointer group"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-100 group-hover:text-white transition-colors">
            {opp.symbol}
          </span>
          <span className="text-xs font-number font-medium text-emerald-400">
            {formatPercent(opp.spreadPercent)}
          </span>
        </div>
        <div className="text-[11px] text-slate-500 mt-0.5 font-number">
          {opp.buyExchange.toUpperCase()}{" "}
          <span className="text-slate-600">&rarr;</span>{" "}
          {opp.sellExchange.toUpperCase()}
        </div>
      </div>
      <div className="text-right shrink-0 ml-3">
        <span className="text-sm font-number font-semibold text-emerald-400">
          +{formatCurrency(opp.netProfit)}
        </span>
        <div className="text-[10px] text-slate-600 mt-0.5 font-number">
          {formatTimeAgo(opp.detectedAt)}
        </div>
      </div>
    </motion.div>
  );
}

/** Single execution row */
function ExecutionRow({ exec, idx }: { exec: ExecutionPlan; idx: number }) {
  const statusVariant =
    exec.status === "completed"
      ? "success"
      : exec.status === "failed"
        ? "danger"
        : exec.status === "executing"
          ? "info"
          : "neutral";

  const statusLabel =
    exec.status === "completed"
      ? "成功"
      : exec.status === "failed"
        ? "失败"
        : exec.status === "executing"
          ? "执行中"
          : exec.status;

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: idx * 0.04, duration: 0.2 }}
      className="flex items-center justify-between rounded-lg bg-dark-800/40 border border-white/[0.04] px-3 py-2.5"
    >
      <div className="flex items-center gap-3 min-w-0">
        <Badge variant={statusVariant} dot size="sm">
          {statusLabel}
        </Badge>
        <div className="min-w-0">
          <span className="text-sm font-medium text-slate-200 block truncate">
            {exec.symbol}
          </span>
          <span className="text-[10px] text-slate-500 font-number">
            {exec.duration > 0 ? formatDuration(exec.duration) : "--"}
          </span>
        </div>
      </div>
      <span
        className={cn(
          "text-sm font-number font-semibold shrink-0 ml-2",
          exec.actualProfit >= 0 ? "text-emerald-400" : "text-red-400"
        )}
      >
        {exec.actualProfit >= 0 ? "+" : ""}
        {formatCurrency(exec.actualProfit)}
      </span>
    </motion.div>
  );
}

/** Alert row for the bottom alert center */
function AlertRow({ alert, idx }: { alert: Alert; idx: number }) {
  const variant =
    alert.severity === "critical"
      ? "danger"
      : alert.severity === "error"
        ? "danger"
        : alert.severity === "warning"
          ? "warning"
          : "info";

  const severityLabel =
    alert.severity === "critical"
      ? "严重"
      : alert.severity === "error"
        ? "错误"
        : alert.severity === "warning"
          ? "警告"
          : "信息";

  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: idx * 0.04, duration: 0.2 }}
      className="flex items-start gap-3 rounded-lg bg-dark-800/40 border border-white/[0.04] px-3 py-2.5"
    >
      <Badge variant={variant} dot size="sm" className="mt-0.5 shrink-0">
        {severityLabel}
      </Badge>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-slate-200 font-medium truncate">
          {alert.title}
        </p>
        <p className="text-[11px] text-slate-500 mt-0.5 line-clamp-1">
          {alert.message}
        </p>
      </div>
      <span className="text-[10px] text-slate-600 font-number shrink-0 mt-0.5">
        {formatTimeAgo(alert.createdAt)}
      </span>
    </motion.div>
  );
}

/** System status row with live indicator */
function SystemStatusRow({
  label,
  status,
  detail,
}: {
  label: string;
  status: "connected" | "degraded" | "disconnected";
  detail?: string;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-white/[0.04] last:border-b-0">
      <div className="flex items-center gap-2">
        <StatusDot status={status} />
        <span className="text-sm text-slate-300">{label}</span>
      </div>
      {detail && (
        <span className="text-xs text-slate-500 font-number">{detail}</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  // --- Data hooks (all fall back to mock data) ---
  const { data: dashboard } = useAnalyticsDashboard();
  const { data: scannerStatus } = useScannerStatus();
  const { data: activeAlerts } = useActiveAlerts();
  const { data: inventorySummary } = useInventorySummary();
  const { data: exchanges } = useExchanges();

  // --- Derived data ---
  const summary = dashboard?.summary;
  const profitTimeline = dashboard?.profitTimeline ?? [];
  const profitByExchange = dashboard?.profitByExchange ?? [];
  const recentExecutions = dashboard?.recentExecutions ?? [];
  const topOpportunities = dashboard?.topOpportunities ?? [];
  const alerts = activeAlerts ?? [];

  const todayPnl = summary?.totalPnl ?? 0;
  const todayTrades = summary?.totalTrades ?? 0;
  const winRate = summary?.winRate ?? 0;
  const winningTrades = summary?.winningTrades ?? 0;
  const losingTrades = summary?.losingTrades ?? 0;

  const exchangeList = (exchanges ?? []) as ExchangeStatus[];
  const onlineExchanges = exchangeList.filter((e) => e.connected).length;
  const totalExchanges = exchangeList.length;

  const criticalAlerts = alerts.filter(
    (a: Alert) => a.severity === "critical" || a.severity === "error"
  ).length;

  // Sparkline data from profit timeline
  const sparklineData = useMemo(
    () => profitTimeline.map((p) => p.cumulativePnl),
    [profitTimeline]
  );

  const successRateSparkline = useMemo(
    () =>
      profitTimeline.map((p) =>
        p.trades > 0 ? ((p.trades - 2) / p.trades) * 100 : 90
      ),
    [profitTimeline]
  );

  // Chart data for profit trend (area chart)
  const profitChartData = useMemo(
    () =>
      profitTimeline.map((p) => ({
        date: (() => {
          const d = new Date(p.period);
          return `${d.getMonth() + 1}/${d.getDate()}`;
        })(),
        value: p.cumulativePnl,
        pnl: p.pnl,
      })),
    [profitTimeline]
  );

  // Chart data for exchange bar chart
  const exchangeBarData = useMemo(
    () =>
      (profitByExchange as ProfitByExchange[]).map((e) => ({
        name: e.exchange.charAt(0).toUpperCase() + e.exchange.slice(1),
        profit: e.pnl,
        trades: e.trades,
      })),
    [profitByExchange]
  );

  // Asset allocation donut
  const assetPieData = useMemo(() => {
    if (!inventorySummary) return [];
    const allocs = (inventorySummary as any).allocations;
    if (allocs) {
      return allocs.map((a: any) => ({
        name: a.exchange.charAt(0).toUpperCase() + a.exchange.slice(1),
        value: a.totalUsd,
      }));
    }
    return [];
  }, [inventorySummary]);

  const totalAssetValue = assetPieData.reduce(
    (sum: number, d: any) => sum + d.value,
    0
  );

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="space-y-5"
    >
      {/* ================================================================= */}
      {/* Row 1 - 6 Key Metric Cards                                        */}
      {/* ================================================================= */}
      <motion.div
        variants={stagger}
        className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3"
      >
        {/* 1. 今日净利润 */}
        <MetricCard
          label="今日净利润"
          value={
            <span
              className={todayPnl >= 0 ? "text-emerald-400" : "text-red-400"}
            >
              {todayPnl >= 0 ? "+" : ""}
              {formatCurrency(todayPnl, { compact: true })}
            </span>
          }
          accent={todayPnl >= 0 ? "emerald" : "red"}
          subValue={
            <span
              className={cn(
                "font-number text-xs",
                todayPnl >= 0 ? "text-emerald-500/70" : "text-red-500/70"
              )}
            >
              {formatPercent(summary?.totalPnlPercent ?? 0)} 收益率
            </span>
          }
        >
          <MiniChart data={sparklineData} width={72} height={28} color="auto" />
        </MetricCard>

        {/* 2. 今日执行次数 */}
        <MetricCard
          label="今日执行次数"
          value={todayTrades}
          subValue={
            <div className="flex items-center gap-2">
              <span className="text-emerald-400/80 font-number">
                {winningTrades} 成功
              </span>
              <span className="text-slate-600">/</span>
              <span className="text-red-400/80 font-number">
                {losingTrades} 失败
              </span>
            </div>
          }
        />

        {/* 3. 成功率 */}
        <MetricCard
          label="成功率"
          value={`${winRate.toFixed(1)}%`}
          accent={winRate >= 90 ? "emerald" : "default"}
          subValue={
            <span className="text-slate-500 font-number">30日均值</span>
          }
        >
          <MiniChart
            data={successRateSparkline}
            width={72}
            height={28}
            color="cyan"
          />
        </MetricCard>

        {/* 4. 活跃机会数 */}
        <MetricCard
          label="活跃机会数"
          value={topOpportunities.length}
          accent="cyan"
          subValue={
            <div className="flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-40" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400" />
              </span>
              <span className="text-cyan-400/70 font-number">实时扫描中</span>
            </div>
          }
        />

        {/* 5. 在线交易所 */}
        <MetricCard
          label="在线交易所"
          value={
            <>
              {onlineExchanges}
              <span className="text-sm text-slate-500 font-normal">
                /{totalExchanges}
              </span>
            </>
          }
          accent={
            onlineExchanges === totalExchanges ? "emerald" : "default"
          }
          subValue={
            <div className="flex gap-1.5">
              {exchangeList.map((ex) => (
                <StatusDot
                  key={ex.exchange}
                  status={
                    ex.status === "healthy"
                      ? "connected"
                      : ex.status === "degraded"
                        ? "degraded"
                        : "disconnected"
                  }
                  size="sm"
                />
              ))}
            </div>
          }
        />

        {/* 6. 高级告警 */}
        <MetricCard
          label="高级告警"
          value={
            <span className={criticalAlerts > 0 ? "text-red-400" : "text-emerald-400"}>
              {criticalAlerts}
            </span>
          }
          accent={criticalAlerts > 0 ? "red" : "emerald"}
          subValue={
            <span
              className={cn(
                "font-number",
                criticalAlerts > 0 ? "text-red-400/70" : "text-slate-500"
              )}
            >
              {criticalAlerts > 0
                ? `${alerts.length} 条未处理`
                : "系统正常"}
            </span>
          }
        />
      </motion.div>

      {/* ================================================================= */}
      {/* Row 2 - Profit Trend + Exchange Profit Distribution               */}
      {/* ================================================================= */}
      <motion.div
        variants={fadeUp}
        className="grid grid-cols-1 lg:grid-cols-5 gap-4"
      >
        {/* Left: 收益趋势图 (3/5) */}
        <div className={cn(cardClass, "lg:col-span-3 p-5")}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-200">
                收益趋势图
              </h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                近30日累计收益
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-number font-semibold text-emerald-400">
                +
                {formatCurrency(
                  profitTimeline.length > 0
                    ? profitTimeline[profitTimeline.length - 1].cumulativePnl
                    : 0,
                  { compact: true }
                )}
              </span>
              <Badge variant="success" size="sm">
                30D
              </Badge>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart
              data={profitChartData}
              margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
            >
              <defs>
                <linearGradient id="profitGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.04)"
                vertical={false}
              />
              <XAxis
                dataKey="date"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#64748b", fontSize: 10 }}
                dy={8}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#64748b", fontSize: 10 }}
                tickFormatter={(v: number) =>
                  formatCurrency(v, { compact: true })
                }
                dx={-4}
                width={58}
              />
              <RechartsTooltip
                content={
                  <ChartTooltip
                    formatter={(v) => formatCurrency(v, { compact: true })}
                  />
                }
                cursor={{ stroke: "rgba(255,255,255,0.08)", strokeWidth: 1 }}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#profitGradient)"
                dot={false}
                activeDot={{
                  r: 4,
                  stroke: "#10b981",
                  strokeWidth: 2,
                  fill: "#0f1419",
                }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Right: 交易所利润分布 (2/5) */}
        <div className={cn(cardClass, "lg:col-span-2 p-5")}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-200">
                交易所利润分布
              </h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                按交易所统计
              </p>
            </div>
            <Badge variant="neutral" size="sm">
              30D
            </Badge>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={exchangeBarData}
              margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.04)"
                vertical={false}
              />
              <XAxis
                dataKey="name"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#64748b", fontSize: 11 }}
                dy={8}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#64748b", fontSize: 10 }}
                tickFormatter={(v: number) =>
                  formatCurrency(v, { compact: true })
                }
                dx={-4}
                width={55}
              />
              <RechartsTooltip
                content={
                  <ChartTooltip
                    formatter={(v) => formatCurrency(v)}
                  />
                }
                cursor={{ fill: "rgba(255,255,255,0.03)" }}
              />
              <Bar dataKey="profit" radius={[4, 4, 0, 0]} maxBarSize={48}>
                {exchangeBarData.map((_, i) => (
                  <Cell
                    key={i}
                    fill={BAR_COLORS[i % BAR_COLORS.length]}
                    fillOpacity={0.85}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </motion.div>

      {/* ================================================================= */}
      {/* Row 3 - Opportunity Feed + Recent Executions + System Status       */}
      {/* ================================================================= */}
      <motion.div
        variants={fadeUp}
        className="grid grid-cols-1 lg:grid-cols-3 gap-4"
      >
        {/* Left: 实时机会流 */}
        <div className={cn(cardClass, "p-5 flex flex-col")}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200">
              实时机会流
            </h3>
            <Badge variant="info" dot size="sm">
              {topOpportunities.length} 实时
            </Badge>
          </div>
          <div className="flex-1 max-h-[340px] overflow-y-auto custom-scrollbar space-y-2 pr-1">
            {topOpportunities.map((opp: ArbitrageOpportunity, idx: number) => (
              <OpportunityRow key={opp.id} opp={opp} idx={idx} />
            ))}
            {topOpportunities.length === 0 && (
              <div className="text-center text-sm text-slate-600 py-10">
                暂无活跃机会
              </div>
            )}
          </div>
        </div>

        {/* Middle: 最新执行记录 */}
        <div className={cn(cardClass, "p-5 flex flex-col")}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200">
              最新执行记录
            </h3>
            <Badge variant="neutral" size="sm">
              最近 {recentExecutions.length} 条
            </Badge>
          </div>
          <div className="flex-1 max-h-[340px] overflow-y-auto custom-scrollbar space-y-2 pr-1">
            {recentExecutions.map((exec: ExecutionPlan, idx: number) => (
              <ExecutionRow key={exec.id} exec={exec} idx={idx} />
            ))}
            {recentExecutions.length === 0 && (
              <div className="text-center text-sm text-slate-600 py-10">
                暂无执行记录
              </div>
            )}
          </div>
        </div>

        {/* Right: 系统状态 */}
        <div className={cn(cardClass, "p-5 flex flex-col")}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200">
              系统状态
            </h3>
            <StatusDot
              status={
                exchangeList.every((e) => e.status === "healthy")
                  ? "connected"
                  : exchangeList.some((e) => e.status === "down")
                    ? "disconnected"
                    : "degraded"
              }
              label={
                exchangeList.every((e) => e.status === "healthy")
                  ? "正常"
                  : "异常"
              }
            />
          </div>

          {/* Exchange connectivity */}
          <div className="mb-4">
            <p className="text-[11px] text-slate-500 uppercase tracking-wider mb-2">
              交易所连接
            </p>
            {exchangeList.map((ex) => (
              <SystemStatusRow
                key={ex.exchange}
                label={ex.name}
                status={
                  ex.status === "healthy"
                    ? "connected"
                    : ex.status === "degraded"
                      ? "degraded"
                      : "disconnected"
                }
                detail={`${ex.latencyMs}ms`}
              />
            ))}
          </div>

          {/* Scanner status */}
          <div className="mb-4">
            <p className="text-[11px] text-slate-500 uppercase tracking-wider mb-2">
              扫描引擎
            </p>
            <SystemStatusRow
              label="跨所扫描"
              status={scannerStatus?.is_running ? "connected" : "disconnected"}
              detail={
                scannerStatus?.cross_exchange
                  ? `${scannerStatus.cross_exchange.last_scan_duration_ms.toFixed(1)}ms`
                  : "--"
              }
            />
            <SystemStatusRow
              label="三角套利"
              status={scannerStatus?.is_running ? "connected" : "disconnected"}
              detail={
                scannerStatus?.triangular
                  ? `${scannerStatus.triangular.last_scan_duration_ms.toFixed(1)}ms`
                  : "--"
              }
            />
          </div>

          {/* Data freshness & risk engine */}
          <div>
            <p className="text-[11px] text-slate-500 uppercase tracking-wider mb-2">
              系统组件
            </p>
            <SystemStatusRow
              label="数据新鲜度"
              status="connected"
              detail={
                scannerStatus?.cross_exchange
                  ? `${((Date.now() / 1000 - scannerStatus.cross_exchange.last_scan_at)).toFixed(0)}s`
                  : "--"
              }
            />
            <SystemStatusRow
              label="风控引擎"
              status="connected"
              detail="活跃"
            />
            <SystemStatusRow
              label="WebSocket"
              status="connected"
              detail={`${totalExchanges} 通道`}
            />
          </div>
        </div>
      </motion.div>

      {/* ================================================================= */}
      {/* Row 4 - Alert Center + Asset Distribution                          */}
      {/* ================================================================= */}
      <motion.div
        variants={fadeUp}
        className="grid grid-cols-1 lg:grid-cols-2 gap-4"
      >
        {/* Left: 告警中心 */}
        <div className={cn(cardClass, "p-5")}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200">
              告警中心
            </h3>
            <Badge
              variant={criticalAlerts > 0 ? "danger" : "neutral"}
              dot
              size="sm"
            >
              {alerts.length} 条未处理
            </Badge>
          </div>
          <div className="space-y-2">
            {alerts.slice(0, 5).map((alert: Alert, idx: number) => (
              <AlertRow key={alert.id} alert={alert} idx={idx} />
            ))}
            {alerts.length === 0 && (
              <div className="text-center text-sm text-slate-600 py-8">
                <span className="text-emerald-500/80">&#10003;</span>{" "}
                暂无活跃告警
              </div>
            )}
          </div>
        </div>

        {/* Right: 资产分布 */}
        <div className={cn(cardClass, "p-5")}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200">
              资产分布
            </h3>
            <span className="text-xs font-number text-slate-400">
              {formatCurrency(totalAssetValue, { compact: true })}
            </span>
          </div>
          <div className="relative">
            <ResponsiveContainer width="100%" height={210}>
              <PieChart>
                <Pie
                  data={assetPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={58}
                  outerRadius={85}
                  paddingAngle={2}
                  dataKey="value"
                  stroke="none"
                >
                  {assetPieData.map((_: any, i: number) => (
                    <Cell
                      key={i}
                      fill={DONUT_COLORS[i % DONUT_COLORS.length]}
                    />
                  ))}
                </Pie>
                <RechartsTooltip
                  content={
                    <ChartTooltip
                      formatter={(v) => formatCurrency(v, { compact: true })}
                    />
                  }
                />
              </PieChart>
            </ResponsiveContainer>
            {/* Center label */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none" style={{ top: 0, height: 210 }}>
              <span className="text-lg font-bold text-white font-number">
                {formatCurrency(totalAssetValue, { compact: true })}
              </span>
              <span className="text-[10px] text-slate-500 uppercase tracking-wider">
                总资产
              </span>
            </div>
          </div>
          {/* Legend */}
          <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5 mt-2">
            {assetPieData.map((entry: any, i: number) => {
              const pct =
                totalAssetValue > 0
                  ? ((entry.value / totalAssetValue) * 100).toFixed(1)
                  : "0";
              return (
                <div
                  key={i}
                  className="flex items-center gap-1.5 text-xs text-slate-400"
                >
                  <span
                    className="h-2 w-2 rounded-full shrink-0"
                    style={{
                      backgroundColor: DONUT_COLORS[i % DONUT_COLORS.length],
                    }}
                  />
                  <span>{entry.name}</span>
                  <span className="font-number text-slate-500">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
