"use client";

import React, { useState, useMemo } from "react";
import { motion } from "framer-motion";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from "recharts";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  formatCurrency,
  formatPercent,
  formatNumber,
  cn,
} from "@/lib/utils";
import {
  mockBalances,
  mockAllocations,
  mockInventoryFullSummary,
  mockRebalanceSuggestions,
  mockInventoryExposure,
} from "@/lib/mock-data";
import type { Balance, ExchangeAllocation, RebalanceSuggestion } from "@/types";

// ---------------------------------------------------------------------------
// Animation variants
// ---------------------------------------------------------------------------

const stagger = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06 },
  },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: "easeOut" as const } },
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EXCHANGE_COLORS: Record<string, string> = {
  binance: "#f59e0b",
  okx: "#3b82f6",
  bybit: "#a78bfa",
};

const EXCHANGE_LABELS: Record<string, string> = {
  binance: "Binance",
  okx: "OKX",
  bybit: "Bybit",
};

const ASSET_COLORS: Record<string, string> = {
  USDT: "#22d3ee",
  BTC: "#f59e0b",
  ETH: "#3b82f6",
  SOL: "#a78bfa",
  DOGE: "#fb923c",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildAssetDistribution(balances: Balance[]) {
  const byAsset: Record<string, { total: number; usdValue: number; exchanges: Record<string, { amount: number; usdValue: number }> }> = {};
  for (const b of balances) {
    if (!byAsset[b.asset]) {
      byAsset[b.asset] = { total: 0, usdValue: 0, exchanges: {} };
    }
    byAsset[b.asset].total += b.total;
    byAsset[b.asset].usdValue += b.usdValue;
    byAsset[b.asset].exchanges[b.exchange] = { amount: b.total, usdValue: b.usdValue };
  }
  return Object.entries(byAsset)
    .map(([asset, data]) => ({ asset, ...data }))
    .sort((a, b) => b.usdValue - a.usdValue);
}

function calculateHHI(allocations: ExchangeAllocation[]): number {
  const total = allocations.reduce((s, a) => s + a.totalUsd, 0);
  if (total === 0) return 0;
  const shares = allocations.map((a) => (a.totalUsd / total) * 100);
  return shares.reduce((s, share) => s + share * share, 0);
}

// ---------------------------------------------------------------------------
// Rebalance status
// ---------------------------------------------------------------------------

type RebalanceStatus = "PENDING" | "APPROVED" | "EXECUTED" | "DISMISSED";

const REBALANCE_STATUS_LABELS: Record<RebalanceStatus, string> = {
  PENDING: "待处理",
  APPROVED: "已批准",
  EXECUTED: "已执行",
  DISMISSED: "已忽略",
};

// ---------------------------------------------------------------------------
// Chart Tooltips
// ---------------------------------------------------------------------------

const PieTooltip = ({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; payload: { color?: string } }>;
}) => {
  if (!active || !payload?.length) return null;
  const entry = payload[0];
  return (
    <div className="rounded-lg bg-dark-800 border border-white/[0.1] px-3 py-2 shadow-xl">
      <p className="text-[10px] text-slate-500 mb-0.5">{entry.name}</p>
      <p className="text-sm font-semibold font-mono text-slate-200">
        {formatCurrency(entry.value, { compact: true })}
      </p>
    </div>
  );
};

const BarTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg bg-dark-800 border border-white/[0.1] px-3 py-2 shadow-xl">
      <p className="text-[10px] text-slate-500 mb-0.5">{label}</p>
      <p className="text-sm font-semibold font-mono text-slate-200">
        {formatCurrency(payload[0].value, { compact: true })}
      </p>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function InventoryPage() {
  const [rebalanceStatuses, setRebalanceStatuses] = useState<Record<string, RebalanceStatus>>({});

  const summary = mockInventoryFullSummary;
  const allocations = mockAllocations;
  const allBalances = mockBalances;
  const exposure = mockInventoryExposure;

  // Derived values
  const totalPortfolioValue = summary.total_value_usdt;
  const numExchanges = summary.exchange_count;
  const numAssets = summary.asset_count;
  const stablecoinBalance = summary.stablecoin_balance;

  // Asset distribution for bar chart
  const assetDistribution = useMemo(() => buildAssetDistribution(allBalances), []);

  // Donut chart data (per exchange)
  const donutData = allocations.map((a) => ({
    name: EXCHANGE_LABELS[a.exchange] || a.exchange,
    value: a.totalUsd,
    color: EXCHANGE_COLORS[a.exchange],
  }));

  // Horizontal bar chart data (per asset)
  const assetBarData = assetDistribution.map((a) => ({
    name: a.asset,
    value: a.usdValue,
    color: ASSET_COLORS[a.asset] || "#64748b",
  }));

  // HHI concentration risk
  const hhiScore = calculateHHI(allocations);
  const hhiNormalized = Math.min(hhiScore / 10000, 1); // 10000 is max (100% on one exchange)
  const hhiRisk = hhiScore < 3333 ? "低" : hhiScore < 5000 ? "中" : "高";
  const hhiColor = hhiScore < 3333 ? "text-emerald-400" : hhiScore < 5000 ? "text-yellow-400" : "text-red-400";

  // Rebalance helpers
  const getRebalanceStatus = (id: string): RebalanceStatus => rebalanceStatuses[id] || "PENDING";
  const setStatus = (id: string, status: RebalanceStatus) => {
    setRebalanceStatuses((prev) => ({ ...prev, [id]: status }));
  };

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      {/* ================================================================= */}
      {/* Header                                                            */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp}>
        <h1 className="text-xl font-semibold text-white">库存管理</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          资产余额、资金分布与再平衡管理
        </p>
      </motion.div>

      {/* ================================================================= */}
      {/* Top Stat Cards (4)                                                */}
      {/* ================================================================= */}
      <motion.div
        variants={fadeUp}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        <StatCard
          label="总资产"
          value={formatCurrency(totalPortfolioValue, { compact: true })}
          suffix="USDT"
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
            </svg>
          }
        />
        <StatCard
          label="交易所数量"
          value={numExchanges}
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 20h20M5 20V8l7-5 7 5v12" />
              <path d="M9 20v-4h6v4" />
            </svg>
          }
        />
        <StatCard
          label="币种数量"
          value={numAssets}
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M8 12h8M12 8v8" />
            </svg>
          }
        />
        <StatCard
          label="稳定币余额"
          value={formatCurrency(stablecoinBalance, { compact: true })}
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
            </svg>
          }
        />
      </motion.div>

      {/* ================================================================= */}
      {/* Main 2-column layout                                              */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp} className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* ============================================================= */}
        {/* LEFT COLUMN (60%) - Exchange Asset Cards                       */}
        {/* ============================================================= */}
        <div className="lg:col-span-3 space-y-4">
          {allocations.map((alloc) => (
            <ExchangeAssetCard
              key={alloc.exchange}
              alloc={alloc}
              totalPortfolioValue={totalPortfolioValue}
              balances={allBalances.filter((b) => b.exchange === alloc.exchange)}
            />
          ))}
        </div>

        {/* ============================================================= */}
        {/* RIGHT COLUMN (40%) - Charts & Risk                            */}
        {/* ============================================================= */}
        <div className="lg:col-span-2 space-y-4">
          {/* Donut chart - Exchange allocation */}
          <Card>
            <CardHeader>资金分布图</CardHeader>
            <CardContent>
              <div className="relative">
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={donutData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={90}
                      paddingAngle={2}
                      dataKey="value"
                      stroke="none"
                    >
                      {donutData.map((entry, index) => (
                        <Cell key={index} fill={entry.color || "#64748b"} fillOpacity={0.85} />
                      ))}
                    </Pie>
                    <RechartsTooltip content={<PieTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  <span className="text-lg font-semibold text-white font-mono">
                    {formatCurrency(totalPortfolioValue, { compact: true })}
                  </span>
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider">
                    总价值
                  </span>
                </div>
              </div>

              {/* Legend */}
              <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 mt-2 px-2">
                {donutData.map((entry, index) => {
                  const total = donutData.reduce((s, d) => s + d.value, 0);
                  const pct = total > 0 ? ((entry.value / total) * 100).toFixed(1) : "0";
                  return (
                    <div key={index} className="flex items-center gap-1.5 text-xs text-slate-400">
                      <span
                        className="h-2 w-2 rounded-full shrink-0"
                        style={{ backgroundColor: entry.color }}
                      />
                      <span>{entry.name}</span>
                      <span className="font-mono text-slate-500">{pct}%</span>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Horizontal bar chart - Asset allocation */}
          <Card>
            <CardHeader>币种分布图</CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart
                  data={assetBarData}
                  layout="vertical"
                  margin={{ top: 0, right: 4, left: 0, bottom: 0 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="rgba(255,255,255,0.04)"
                    horizontal={false}
                  />
                  <XAxis
                    type="number"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#64748b", fontSize: 10 }}
                    tickFormatter={(v: number) => formatCurrency(v, { compact: true })}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#94a3b8", fontSize: 11, fontWeight: 500 }}
                    width={50}
                  />
                  <RechartsTooltip
                    content={<BarTooltip />}
                    cursor={{ fill: "rgba(255,255,255,0.03)" }}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={24}>
                    {assetBarData.map((entry, index) => (
                      <Cell key={index} fill={entry.color} fillOpacity={0.8} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* HHI Concentration Risk */}
          <Card>
            <CardHeader>集中度风险指标</CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-slate-500 mb-1">HHI 指数</p>
                    <p className={cn("text-2xl font-semibold font-mono", hhiColor)}>
                      {hhiScore.toFixed(0)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-slate-500 mb-1">风险等级</p>
                    <Badge
                      variant={hhiScore < 3333 ? "success" : hhiScore < 5000 ? "warning" : "danger"}
                      size="md"
                    >
                      {hhiRisk}
                    </Badge>
                  </div>
                </div>

                {/* HHI gauge bar */}
                <div className="space-y-2">
                  <div className="h-3 rounded-full bg-dark-700 overflow-hidden relative">
                    <motion.div
                      className={cn(
                        "h-full rounded-full",
                        hhiScore < 3333
                          ? "bg-emerald-500"
                          : hhiScore < 5000
                            ? "bg-yellow-500"
                            : "bg-red-500"
                      )}
                      initial={{ width: 0 }}
                      animate={{ width: `${hhiNormalized * 100}%` }}
                      transition={{ duration: 0.8, ease: "easeOut" }}
                    />
                    {/* Threshold markers */}
                    <div className="absolute top-0 bottom-0 w-px bg-white/20" style={{ left: "33.33%" }} />
                    <div className="absolute top-0 bottom-0 w-px bg-white/20" style={{ left: "50%" }} />
                  </div>
                  <div className="flex justify-between text-[10px] text-slate-600">
                    <span>0 (均衡)</span>
                    <span>3333</span>
                    <span>5000</span>
                    <span>10000 (集中)</span>
                  </div>
                </div>

                <p className="text-xs text-slate-500 leading-relaxed">
                  HHI (赫芬达尔-赫希曼指数) 衡量资产在交易所之间的集中度。
                  低于 3333 表示资金分散良好，高于 5000 表示过度集中于少数交易所。
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </motion.div>

      {/* ================================================================= */}
      {/* Bottom: Rebalance Suggestions Table                               */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp}>
        <Card>
          <CardHeader>再平衡建议</CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/[0.06]">
                    <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-3">币种</th>
                    <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-3">来源交易所</th>
                    <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-3">目标交易所</th>
                    <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-3">建议数量</th>
                    <th className="text-left text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-3">原因</th>
                    <th className="text-right text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-3">偏离度</th>
                    <th className="text-center text-xs font-medium text-slate-500 uppercase tracking-wider px-4 py-3">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {mockRebalanceSuggestions.map((sug) => {
                    const status = getRebalanceStatus(sug.id);
                    const deviation = ((sug.usdValue / totalPortfolioValue) * 100);

                    return (
                      <motion.tr
                        key={sug.id}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className={cn(
                          "border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors",
                          status === "DISMISSED" && "opacity-50"
                        )}
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-white">{sug.asset}</span>
                            <Badge
                              variant={sug.priority === "high" ? "danger" : sug.priority === "medium" ? "warning" : "info"}
                              size="sm"
                            >
                              {sug.priority === "high" ? "高" : sug.priority === "medium" ? "中" : "低"}
                            </Badge>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span
                              className="h-2 w-2 rounded-full"
                              style={{ backgroundColor: EXCHANGE_COLORS[sug.fromExchange] || "#64748b" }}
                            />
                            <span className="text-slate-300">{EXCHANGE_LABELS[sug.fromExchange] || sug.fromExchange}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span
                              className="h-2 w-2 rounded-full"
                              style={{ backgroundColor: EXCHANGE_COLORS[sug.toExchange] || "#64748b" }}
                            />
                            <span className="text-slate-300">{EXCHANGE_LABELS[sug.toExchange] || sug.toExchange}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div>
                            <span className="font-mono text-white">{formatNumber(sug.amount)} {sug.asset}</span>
                            <p className="text-xs font-mono text-slate-500">{formatCurrency(sug.usdValue)}</p>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <p className="text-xs text-slate-400 max-w-[240px] leading-relaxed">{sug.reason}</p>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className={cn(
                            "font-mono text-sm",
                            deviation > 3 ? "text-yellow-400" : "text-slate-400"
                          )}>
                            {deviation.toFixed(2)}%
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-center gap-2">
                            {status === "PENDING" ? (
                              <>
                                <Button
                                  variant="primary"
                                  size="sm"
                                  onClick={() => setStatus(sug.id, "APPROVED")}
                                >
                                  接受
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setStatus(sug.id, "DISMISSED")}
                                >
                                  忽略
                                </Button>
                              </>
                            ) : (
                              <Badge
                                variant={
                                  status === "APPROVED"
                                    ? "success"
                                    : status === "EXECUTED"
                                      ? "info"
                                      : "neutral"
                                }
                                dot
                                size="sm"
                              >
                                {REBALANCE_STATUS_LABELS[status]}
                              </Badge>
                            )}
                          </div>
                        </td>
                      </motion.tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Exchange Asset Card
// ---------------------------------------------------------------------------

function ExchangeAssetCard({
  alloc,
  totalPortfolioValue,
  balances,
}: {
  alloc: ExchangeAllocation;
  totalPortfolioValue: number;
  balances: Balance[];
}) {
  const statusVariant = alloc.status === "connected"
    ? "success"
    : alloc.status === "degraded"
      ? "warning"
      : "danger";

  const statusLabel = alloc.status === "connected"
    ? "已连接"
    : alloc.status === "degraded"
      ? "降级"
      : "断开";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card>
        <CardContent>
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <span
                className="h-3 w-3 rounded-full"
                style={{ backgroundColor: EXCHANGE_COLORS[alloc.exchange] }}
              />
              <h3 className="text-base font-semibold text-white">
                {EXCHANGE_LABELS[alloc.exchange] || alloc.exchange}
              </h3>
              <Badge variant={statusVariant} size="sm" dot>
                {statusLabel}
              </Badge>
            </div>
            <div className="text-right">
              <p className="text-lg font-semibold font-mono text-white">
                {formatCurrency(alloc.totalUsd, { compact: true })}
              </p>
              <p className="text-xs text-slate-500 font-mono">
                {alloc.percentOfTotal.toFixed(1)}% 总资产
              </p>
            </div>
          </div>

          {/* Portfolio share progress bar */}
          <div className="mb-4">
            <Progress
              value={alloc.percentOfTotal}
              variant={
                alloc.exchange === "binance"
                  ? "warning"
                  : alloc.exchange === "okx"
                    ? "default"
                    : "accent"
              }
              size="sm"
            />
          </div>

          {/* Asset breakdown table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  <th className="text-left text-[10px] font-medium text-slate-600 uppercase tracking-wider px-3 py-2">币种</th>
                  <th className="text-right text-[10px] font-medium text-slate-600 uppercase tracking-wider px-3 py-2">可用</th>
                  <th className="text-right text-[10px] font-medium text-slate-600 uppercase tracking-wider px-3 py-2">锁定</th>
                  <th className="text-right text-[10px] font-medium text-slate-600 uppercase tracking-wider px-3 py-2">总计</th>
                  <th className="text-right text-[10px] font-medium text-slate-600 uppercase tracking-wider px-3 py-2">USD价值</th>
                </tr>
              </thead>
              <tbody>
                {balances.map((b) => (
                  <tr
                    key={`${b.exchange}-${b.asset}`}
                    className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span
                          className="h-1.5 w-1.5 rounded-full"
                          style={{ backgroundColor: ASSET_COLORS[b.asset] || "#64748b" }}
                        />
                        <span className="font-semibold text-white">{b.asset}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-slate-300">
                      {formatNumber(b.free, { decimals: b.asset === "DOGE" ? 0 : 4 })}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className={cn(
                        "font-mono",
                        b.locked > 0 ? "text-yellow-400" : "text-slate-600"
                      )}>
                        {formatNumber(b.locked, { decimals: b.asset === "DOGE" ? 0 : 4 })}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-slate-200">
                      {formatNumber(b.total, { decimals: b.asset === "DOGE" ? 0 : 4 })}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-white font-medium">
                      {formatCurrency(b.usdValue)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
