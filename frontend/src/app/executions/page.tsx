"use client";

import React, { useState, useMemo, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { StatCard } from "@/components/ui/stat-card";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabPanel } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/ui/data-table";
import {
  formatCurrency,
  formatPercent,
  formatTimeAgo,
  formatDuration,
  formatDate,
  cn,
} from "@/lib/utils";
import { mockExecutions, mockExecutionDetails, mockRiskDecision, mockAuditEntries } from "@/lib/mock-data";
import type { ExecutionPlan, ExecutionLeg, ExecutionDetail, AuditEntry } from "@/types";

// ---------------------------------------------------------------------------
// State machine steps for visualization
// ---------------------------------------------------------------------------

const pipelineStates = [
  { key: "created", label: "创建" },
  { key: "risk_check", label: "风控" },
  { key: "ready", label: "就绪" },
  { key: "executing", label: "执行中" },
  { key: "completed", label: "完成" },
] as const;

function getPipelineIndex(exec: ExecutionPlan): number {
  if (exec.status === "completed") return 4;
  if (exec.status === "failed") {
    const filledLegs = exec.legs.filter((l) => l.status === "filled").length;
    if (filledLegs > 0) return 3;
    return 2;
  }
  if (exec.status === "cancelled" || exec.status === "timeout") return 4;
  const filledLegs = exec.legs.filter((l) => l.status === "filled").length;
  const openLegs = exec.legs.filter((l) => l.status === "open").length;
  if (filledLegs > 0 || openLegs > 0) return 3;
  return 2;
}

// ---------------------------------------------------------------------------
// Derived data
// ---------------------------------------------------------------------------

const activeExecutions = mockExecutions.filter(
  (e) => e.status === "executing" || e.status === "partial" || e.status === "pending"
);

const historyExecutions = mockExecutions.filter(
  (e) => e.status === "completed" || e.status === "failed" || e.status === "cancelled" || e.status === "timeout"
);

const totalCount = mockExecutions.length;
const successfulCount = mockExecutions.filter((e) => e.status === "completed").length;
const failedCount = mockExecutions.filter((e) => e.status === "failed").length;
const successRate = totalCount > 0 ? ((successfulCount / totalCount) * 100) : 0;
const totalNetProfit = mockExecutions.reduce((sum, e) => sum + e.actualProfit, 0);
const avgDuration =
  mockExecutions
    .filter((e) => e.duration > 0)
    .reduce((sum, e) => sum + e.duration, 0) /
  Math.max(1, mockExecutions.filter((e) => e.duration > 0).length);

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
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" as const } },
};

// ---------------------------------------------------------------------------
// Label maps
// ---------------------------------------------------------------------------

const execStatusLabels: Record<string, string> = {
  completed: "已完成",
  failed: "失败",
  executing: "执行中",
  partial: "部分成交",
  pending: "提交中",
  cancelled: "已中止",
  timeout: "已超时",
};

const legStatusLabels: Record<string, string> = {
  filled: "已成交",
  open: "挂单中",
  rejected: "已拒绝",
  pending: "待处理",
  cancelled: "已取消",
};

const sideLabels: Record<string, string> = {
  buy: "买入",
  sell: "卖出",
  BUY: "买入",
  SELL: "卖出",
};

const strategyLabels: Record<string, string> = {
  spatial: "跨交易所",
  triangular: "三角套利",
  funding_rate: "期现套利",
  statistical: "统计套利",
  cross_exchange: "跨交易所",
};

const modeLabels: Record<string, string> = {
  live: "实盘",
  paper: "模拟",
  backtest: "回测",
};

// ---------------------------------------------------------------------------
// History Table Columns
// ---------------------------------------------------------------------------

type HistoryRow = ExecutionPlan & Record<string, unknown>;

const historyColumns: Column<HistoryRow>[] = [
  {
    key: "id",
    header: "ID",
    sortable: true,
    render: (row) => (
      <span className="text-xs text-slate-400 font-mono">
        {row.id.slice(-6)}
      </span>
    ),
  },
  {
    key: "strategyType",
    header: "策略",
    sortable: true,
    render: (row) => {
      const colors: Record<string, "info" | "warning" | "success" | "neutral"> = {
        spatial: "info",
        triangular: "warning",
        funding_rate: "success",
        statistical: "neutral",
        cross_exchange: "info",
      };
      return (
        <Badge variant={colors[row.strategyType] ?? "neutral"} size="sm">
          {strategyLabels[row.strategyType] ?? row.strategyType}
        </Badge>
      );
    },
  },
  {
    key: "symbol",
    header: "交易对",
    sortable: true,
    render: (row) => (
      <span className="text-sm font-medium text-slate-200">{row.symbol}</span>
    ),
  },
  {
    key: "mode",
    header: "模式",
    render: () => (
      <Badge variant="neutral" size="sm">模拟</Badge>
    ),
  },
  {
    key: "status",
    header: "状态",
    sortable: true,
    render: (row) => {
      const variant =
        row.status === "completed"
          ? "success"
          : row.status === "failed"
            ? "danger"
            : row.status === "executing"
              ? "info"
              : "neutral";
      return (
        <Badge variant={variant} dot size="sm">
          {execStatusLabels[row.status] ?? row.status}
        </Badge>
      );
    },
  },
  {
    key: "expectedProfit",
    header: "计划利润",
    align: "right",
    sortable: true,
    render: (row) => (
      <span className="text-xs font-mono text-slate-400">
        {formatCurrency(row.expectedProfit)}
      </span>
    ),
  },
  {
    key: "actualProfit",
    header: "实际利润",
    align: "right",
    sortable: true,
    render: (row) => (
      <span
        className={cn(
          "text-sm font-mono font-medium",
          row.actualProfit >= 0 ? "text-emerald-400" : "text-red-400"
        )}
      >
        {row.actualProfit !== 0 ? formatCurrency(row.actualProfit) : "--"}
      </span>
    ),
  },
  {
    key: "slippage",
    header: "滑点",
    align: "right",
    sortable: true,
    render: (row) => (
      <span
        className={cn(
          "text-xs font-mono",
          row.slippage > 0.01 ? "text-yellow-400" : "text-slate-500"
        )}
      >
        {row.slippage > 0 ? formatPercent(row.slippage, { decimals: 4 }) : "--"}
      </span>
    ),
  },
  {
    key: "duration",
    header: "耗时",
    align: "right",
    sortable: true,
    render: (row) => (
      <span className="text-xs font-mono text-slate-400">
        {row.duration > 0 ? formatDuration(row.duration) : "--"}
      </span>
    ),
  },
  {
    key: "startedAt",
    header: "开始时间",
    sortable: true,
    render: (row) => (
      <span className="text-xs text-slate-400 font-mono whitespace-nowrap">
        {formatDate(row.startedAt, { format: "datetime" })}
      </span>
    ),
  },
];

// ---------------------------------------------------------------------------
// Risk check mock data for detail view
// ---------------------------------------------------------------------------

const riskCheckResults = mockRiskDecision.results;

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ExecutionsPage() {
  const [activeTab, setActiveTab] = useState("active");
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const pageSize = 8;

  const tabs = [
    { id: "active", label: "活跃执行", count: activeExecutions.length },
    { id: "history", label: "历史记录", count: historyExecutions.length },
  ];

  const paginatedHistory = useMemo(() => {
    const start = (historyPage - 1) * pageSize;
    return historyExecutions.slice(start, start + pageSize);
  }, [historyPage]);

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
        <h1 className="text-xl font-semibold text-white">执行记录</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          监控活跃交易执行并查看完整历史记录
        </p>
      </motion.div>

      {/* ================================================================= */}
      {/* Summary Stat Cards (6)                                            */}
      {/* ================================================================= */}
      <motion.div
        variants={fadeUp}
        className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4"
      >
        <StatCard
          label="总执行数"
          value={totalCount}
          icon={
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4 4v12h12" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M4 14l4-4 3 2 5-6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
        />
        <StatCard
          label="成功数"
          value={successfulCount}
          icon={
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M10 2a8 8 0 100 16 8 8 0 000-16z" />
              <path d="M7 10l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
        />
        <StatCard
          label="失败数"
          value={failedCount}
          icon={
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M10 2a8 8 0 100 16 8 8 0 000-16z" />
              <path d="M13 7l-6 6M7 7l6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
        />
        <StatCard
          label="成功率"
          value={`${successRate.toFixed(1)}%`}
          icon={
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="10" cy="10" r="7" />
              <path d="M10 6v4l3 2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
        />
        <StatCard
          label="总净利润"
          value={formatCurrency(totalNetProfit)}
          icon={
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 15l4-4 3 3 4-5 5 4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
        />
        <StatCard
          label="平均耗时"
          value={`${Math.round(avgDuration)}ms`}
          icon={
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M11 2L5 12h5l-1 6 6-10h-5l1-6z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
        />
      </motion.div>

      {/* ================================================================= */}
      {/* Tabs                                                              */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp}>
        <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />
      </motion.div>

      {/* ================================================================= */}
      {/* Active Tab                                                        */}
      {/* ================================================================= */}
      <TabPanel tabId="active" activeTab={activeTab}>
        {activeExecutions.length === 0 ? (
          <Card padding="lg">
            <div className="text-center text-slate-600 text-sm py-8">
              当前没有进行中的执行
            </div>
          </Card>
        ) : (
          <div className="space-y-4">
            {activeExecutions.map((exec) => (
              <ActiveExecutionCard key={exec.id} exec={exec} />
            ))}
          </div>
        )}
      </TabPanel>

      {/* ================================================================= */}
      {/* History Tab                                                       */}
      {/* ================================================================= */}
      <TabPanel tabId="history" activeTab={activeTab}>
        <div className="space-y-4">
          <DataTable<HistoryRow>
            columns={historyColumns}
            data={paginatedHistory as HistoryRow[]}
            keyExtractor={(row) => row.id}
            onRowClick={(row) =>
              setExpandedRow(expandedRow === row.id ? null : row.id)
            }
            pagination={{
              page: historyPage,
              pageSize,
              total: historyExecutions.length,
              onPageChange: setHistoryPage,
            }}
          />

          <AnimatePresence>
            {expandedRow && (
              <ExecutionDetailDrawer
                exec={historyExecutions.find((e) => e.id === expandedRow)!}
                detail={mockExecutionDetails.find((d) => d.execution_id === expandedRow) ?? null}
                onClose={() => setExpandedRow(null)}
              />
            )}
          </AnimatePresence>
        </div>
      </TabPanel>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Active Execution Card
// ---------------------------------------------------------------------------

function ActiveExecutionCard({ exec }: { exec: ExecutionPlan }) {
  const [elapsed, setElapsed] = useState(0);
  const pipelineIdx = getPipelineIndex(exec);
  const filledLegs = exec.legs.filter((l) => l.status === "filled").length;
  const totalLegs = exec.legs.length;

  useEffect(() => {
    const startTime = new Date(exec.startedAt).getTime();
    const update = () => setElapsed(Date.now() - startTime);
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [exec.startedAt]);

  const stratColors: Record<string, "info" | "warning" | "success" | "neutral"> = {
    spatial: "info",
    triangular: "warning",
    funding_rate: "success",
    statistical: "neutral",
    cross_exchange: "info",
  };

  const exchanges = [...new Set(exec.legs.map((l) => l.exchange))];

  const estimatedPnl = exec.actualProfit !== 0
    ? exec.actualProfit
    : exec.expectedProfit * (filledLegs / Math.max(totalLegs, 1));

  return (
    <Card padding="md" glow="cyan" hover>
      <div className="flex flex-col lg:flex-row lg:items-start gap-6">
        {/* Left: Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-3">
            <Badge variant={stratColors[exec.strategyType] ?? "neutral"} size="md">
              {strategyLabels[exec.strategyType] ?? exec.strategyType}
            </Badge>
            <Badge variant="info" dot size="sm">
              执行中
            </Badge>
          </div>

          <h3 className="text-lg font-semibold text-white mb-1">{exec.symbol}</h3>
          <p className="text-xs text-slate-400 capitalize mb-4">
            {exchanges.join(" / ")}
          </p>

          {/* Stats grid */}
          <div className="grid grid-cols-2 gap-3 text-xs mb-4">
            <div>
              <span className="text-slate-600 uppercase tracking-wider">腿进度</span>
              <p className="text-slate-200 font-mono mt-0.5">
                {filledLegs} / {totalLegs} 已完成
              </p>
            </div>
            <div>
              <span className="text-slate-600 uppercase tracking-wider">成交额</span>
              <p className="text-slate-200 font-mono mt-0.5">
                {formatCurrency(exec.totalVolume, { compact: true })}
              </p>
            </div>
            <div>
              <span className="text-slate-600 uppercase tracking-wider">已耗时</span>
              <p className="text-slate-200 font-mono mt-0.5">
                {formatDuration(elapsed)}
              </p>
            </div>
            <div>
              <span className="text-slate-600 uppercase tracking-wider">预估盈亏</span>
              <p
                className={cn(
                  "font-mono font-medium mt-0.5",
                  estimatedPnl >= 0 ? "text-emerald-400" : "text-red-400"
                )}
              >
                {formatCurrency(estimatedPnl)}
              </p>
            </div>
          </div>

          {/* Leg details */}
          <div className="space-y-1.5">
            {exec.legs.map((leg, i) => (
              <div
                key={leg.id}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-xs",
                  leg.status === "filled"
                    ? "bg-emerald-500/5 border border-emerald-500/10"
                    : leg.status === "open"
                      ? "bg-blue-500/5 border border-blue-500/10"
                      : "bg-dark-800/50 border border-white/[0.04]"
                )}
              >
                <Badge
                  variant={
                    leg.status === "filled"
                      ? "success"
                      : leg.status === "open"
                        ? "info"
                        : "neutral"
                  }
                  size="sm"
                >
                  腿 {i + 1}
                </Badge>
                <span className="text-slate-400 capitalize">{leg.exchange}</span>
                <span
                  className={cn(
                    "font-medium uppercase",
                    leg.side === "buy" ? "text-emerald-400" : "text-red-400"
                  )}
                >
                  {sideLabels[leg.side] ?? leg.side}
                </span>
                <span className="text-slate-300">{leg.symbol}</span>
                <span className="ml-auto font-mono text-slate-400">
                  {leg.status === "filled"
                    ? formatCurrency(leg.cost)
                    : `@ ${formatCurrency(leg.price)}`}
                </span>
                <Badge
                  variant={
                    leg.status === "filled" ? "success" : leg.status === "open" ? "info" : "neutral"
                  }
                  size="sm"
                >
                  {legStatusLabels[leg.status] ?? leg.status}
                </Badge>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Pipeline State Machine */}
        <div className="lg:w-52 shrink-0">
          <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-3 text-center">
            执行流水线
          </p>
          <div className="flex flex-col items-center gap-0">
            {pipelineStates.map((state, i) => {
              const isComplete = i < pipelineIdx;
              const isCurrent = i === pipelineIdx;
              const isFuture = i > pipelineIdx;
              const isFailed = exec.status === "failed" && isCurrent;

              return (
                <React.Fragment key={state.key}>
                  <div className="flex items-center gap-3 relative">
                    <div
                      className={cn(
                        "w-3.5 h-3.5 rounded-full border-2 transition-all duration-300 relative",
                        isComplete && "bg-emerald-400 border-emerald-400",
                        isCurrent && !isFailed && "bg-blue-400 border-blue-400 shadow-[0_0_10px_rgba(59,130,246,0.6)]",
                        isCurrent && isFailed && "bg-red-400 border-red-400 shadow-[0_0_10px_rgba(239,68,68,0.6)]",
                        isFuture && "bg-dark-800 border-slate-600"
                      )}
                    >
                      {isCurrent && !isFailed && (
                        <motion.span
                          className="absolute inset-0 rounded-full bg-blue-400"
                          animate={{ opacity: [0.4, 0, 0.4], scale: [1, 1.8, 1] }}
                          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                        />
                      )}
                    </div>
                    <span
                      className={cn(
                        "text-xs font-medium whitespace-nowrap",
                        isComplete && "text-emerald-400",
                        isCurrent && !isFailed && "text-blue-300",
                        isCurrent && isFailed && "text-red-400",
                        isFuture && "text-slate-600"
                      )}
                    >
                      {state.label}
                    </span>
                  </div>

                  {i < pipelineStates.length - 1 && (
                    <div
                      className={cn(
                        "w-0.5 h-5 ml-[6px] self-start transition-colors duration-300",
                        i < pipelineIdx ? "bg-emerald-400" : "bg-slate-700"
                      )}
                    />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Execution Detail Drawer / Expandable Section
// ---------------------------------------------------------------------------

function ExecutionDetailDrawer({
  exec,
  detail,
  onClose,
}: {
  exec: ExecutionPlan;
  detail: ExecutionDetail | null;
  onClose: () => void;
}) {
  if (!exec) return null;

  // Use Phase 3 detail data if available, otherwise fall back to Phase 1 data
  const auditTrail: AuditEntry[] = detail?.audit_trail ?? mockAuditEntries.slice(0, 6);
  const riskResults = detail?.plan?.risk_check?.results ?? riskCheckResults;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.3, ease: "easeInOut" }}
      className="overflow-hidden"
    >
      <Card padding="md" variant="bordered">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-medium text-white">
              执行详情: {exec.id}
            </h3>
            <Badge
              variant={exec.status === "completed" ? "success" : exec.status === "failed" ? "danger" : "neutral"}
              dot
              size="sm"
            >
              {execStatusLabels[exec.status] ?? exec.status}
            </Badge>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 transition-colors p-1"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Error banner */}
        {exec.error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 mb-5">
            <p className="text-xs text-red-400">{exec.error}</p>
          </div>
        )}

        {/* Section 1: 执行计划 Summary */}
        <div className="mb-5">
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">执行计划</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-3 rounded-lg bg-dark-800/50 border border-white/[0.04]">
            <div>
              <p className="text-[10px] text-slate-600 uppercase tracking-wider">计划收益</p>
              <p className="text-sm font-mono text-slate-300 mt-0.5">
                {formatCurrency(exec.expectedProfit)} ({formatPercent(exec.expectedProfitPercent, { decimals: 4 })})
              </p>
            </div>
            <div>
              <p className="text-[10px] text-slate-600 uppercase tracking-wider">实际收益</p>
              <p
                className={cn(
                  "text-sm font-mono font-medium mt-0.5",
                  exec.actualProfit >= 0 ? "text-emerald-400" : "text-red-400"
                )}
              >
                {formatCurrency(exec.actualProfit)} ({formatPercent(exec.actualProfitPercent, { decimals: 4 })})
              </p>
            </div>
            <div>
              <p className="text-[10px] text-slate-600 uppercase tracking-wider">总手续费</p>
              <p className="text-sm font-mono text-slate-400 mt-0.5">{formatCurrency(exec.totalFees)}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-600 uppercase tracking-wider">总成交额</p>
              <p className="text-sm font-mono text-slate-400 mt-0.5">{formatCurrency(exec.totalVolume, { compact: true })}</p>
            </div>
          </div>
        </div>

        {/* Section 2: 风控检查结果 */}
        <div className="mb-5">
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">风控检查结果</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {riskResults.map((rule, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.04, duration: 0.2 }}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-xs border",
                  rule.passed
                    ? "bg-emerald-500/5 border-emerald-500/10"
                    : "bg-red-500/5 border-red-500/10"
                )}
              >
                <span className={cn(
                  "shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[10px]",
                  rule.passed ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"
                )}>
                  {rule.passed ? "✓" : "✗"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-slate-300 truncate">{rule.rule_name}</p>
                  <p className="text-slate-500 truncate">{rule.reason}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        {/* Section 3: Legs Timeline */}
        <div className="mb-5">
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">执行腿时间线</h4>
          <div className="relative pl-6">
            {/* Vertical line */}
            <div className="absolute left-[7px] top-0 bottom-0 w-0.5 bg-slate-700/50" />

            {exec.legs.map((leg, i) => {
              const isSuccess = leg.status === "filled";
              const isFailed = leg.status === "rejected" || leg.status === "cancelled";
              const slippage = leg.price > 0 && leg.cost > 0 && leg.filled > 0
                ? ((leg.cost / leg.filled - leg.price) / leg.price) * 100
                : 0;

              return (
                <motion.div
                  key={leg.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.08, duration: 0.25 }}
                  className="relative mb-4 last:mb-0"
                >
                  {/* Timeline dot */}
                  <div
                    className={cn(
                      "absolute -left-6 top-2.5 w-3.5 h-3.5 rounded-full border-2 z-10",
                      isSuccess && "bg-emerald-400 border-emerald-400",
                      isFailed && "bg-red-400 border-red-400",
                      !isSuccess && !isFailed && "bg-blue-400 border-blue-400"
                    )}
                  />

                  <div className={cn(
                    "rounded-lg border p-3 ml-2",
                    isSuccess
                      ? "bg-emerald-500/5 border-emerald-500/10"
                      : isFailed
                        ? "bg-red-500/5 border-red-500/10"
                        : "bg-blue-500/5 border-blue-500/10"
                  )}>
                    <div className="flex items-center gap-2 mb-2">
                      <Badge
                        variant={isSuccess ? "success" : isFailed ? "danger" : "info"}
                        size="sm"
                      >
                        腿 {i + 1}
                      </Badge>
                      <span className="text-xs text-slate-400 capitalize">{leg.exchange}</span>
                      <span className="text-xs text-slate-300 font-medium">{leg.symbol}</span>
                      <span
                        className={cn(
                          "text-xs font-medium uppercase",
                          leg.side === "buy" ? "text-emerald-400" : "text-red-400"
                        )}
                      >
                        {sideLabels[leg.side] ?? leg.side}
                      </span>
                      <Badge
                        variant={isSuccess ? "success" : isFailed ? "danger" : "info"}
                        size="sm"
                        className="ml-auto"
                      >
                        {legStatusLabels[leg.status] ?? leg.status}
                      </Badge>
                    </div>

                    <div className="grid grid-cols-3 md:grid-cols-6 gap-2 text-xs">
                      <div>
                        <span className="text-slate-600">计划价格</span>
                        <p className="font-mono text-slate-300 mt-0.5">{formatCurrency(leg.price)}</p>
                      </div>
                      <div>
                        <span className="text-slate-600">实际价格</span>
                        <p className="font-mono text-slate-300 mt-0.5">
                          {leg.filled > 0 && leg.cost > 0
                            ? formatCurrency(leg.cost / leg.filled)
                            : "--"}
                        </p>
                      </div>
                      <div>
                        <span className="text-slate-600">数量</span>
                        <p className="font-mono text-slate-300 mt-0.5">
                          {leg.filled > 0 ? `${leg.filled} / ${leg.quantity}` : leg.quantity.toString()}
                        </p>
                      </div>
                      <div>
                        <span className="text-slate-600">手续费</span>
                        <p className="font-mono text-slate-400 mt-0.5">
                          {leg.fee > 0 ? formatCurrency(leg.fee) : "--"}
                        </p>
                      </div>
                      <div>
                        <span className="text-slate-600">滑点</span>
                        <p className={cn(
                          "font-mono mt-0.5",
                          Math.abs(slippage) > 0.01 ? "text-yellow-400" : "text-slate-400"
                        )}>
                          {slippage !== 0 ? `${slippage.toFixed(4)}%` : "--"}
                        </p>
                      </div>
                      <div>
                        <span className="text-slate-600">延迟</span>
                        <p className="font-mono text-slate-400 mt-0.5">
                          {leg.latencyMs > 0 ? `${leg.latencyMs}ms` : "--"}
                        </p>
                      </div>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Section 4: 状态迁移记录 */}
        <div className="mb-5">
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">状态迁移记录</h4>
          <div className="space-y-1">
            {auditTrail
              .filter((a) => a.event_type === "STATE_TRANSITION")
              .map((entry, idx) => (
                <motion.div
                  key={entry.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: idx * 0.05 }}
                  className="flex items-center gap-3 text-xs px-3 py-2 rounded-lg bg-dark-800/30 border border-white/[0.03]"
                >
                  <span className="text-slate-600 font-mono">
                    {new Date(entry.timestamp * 1000).toLocaleTimeString("en-US", {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                  <svg className="w-3 h-3 text-slate-600" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M3 6h6M7 4l2 2-2 2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span className="text-slate-300">{entry.action}</span>
                </motion.div>
              ))}
          </div>
        </div>

        {/* Section 5: 最终结果 Summary */}
        <div className="mb-5">
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">最终结果</h4>
          <div className={cn(
            "rounded-lg border p-4",
            exec.status === "completed"
              ? "bg-emerald-500/5 border-emerald-500/10"
              : exec.status === "failed"
                ? "bg-red-500/5 border-red-500/10"
                : "bg-dark-800/50 border-white/[0.04]"
          )}>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-xs">
              <div>
                <span className="text-slate-600">状态</span>
                <p className={cn(
                  "font-medium mt-0.5",
                  exec.status === "completed" ? "text-emerald-400" : "text-red-400"
                )}>
                  {execStatusLabels[exec.status] ?? exec.status}
                </p>
              </div>
              <div>
                <span className="text-slate-600">净利润</span>
                <p className={cn(
                  "font-mono font-medium mt-0.5",
                  exec.actualProfit >= 0 ? "text-emerald-400" : "text-red-400"
                )}>
                  {formatCurrency(exec.actualProfit)}
                </p>
              </div>
              <div>
                <span className="text-slate-600">总手续费</span>
                <p className="font-mono text-slate-400 mt-0.5">{formatCurrency(exec.totalFees)}</p>
              </div>
              <div>
                <span className="text-slate-600">总滑点</span>
                <p className={cn(
                  "font-mono mt-0.5",
                  exec.slippage > 0.01 ? "text-yellow-400" : "text-slate-400"
                )}>
                  {exec.slippage > 0 ? formatPercent(exec.slippage, { decimals: 4 }) : "0%"}
                </p>
              </div>
              <div>
                <span className="text-slate-600">执行时间</span>
                <p className="font-mono text-slate-400 mt-0.5">
                  {exec.duration > 0 ? formatDuration(exec.duration) : "--"}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Section 6: 审计日志 */}
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">审计日志</h4>
          <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
            {auditTrail.map((entry, idx) => {
              const eventColors: Record<string, string> = {
                EXECUTION_CREATED: "text-blue-400",
                RISK_CHECK: "text-cyan-400",
                STATE_TRANSITION: "text-purple-400",
                LEG_SUBMITTED: "text-yellow-400",
                LEG_FILLED: "text-emerald-400",
                LEG_FAILED: "text-red-400",
              };

              return (
                <motion.div
                  key={entry.id}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.03 }}
                  className="flex items-start gap-3 text-xs px-3 py-1.5 rounded bg-dark-800/20 border border-white/[0.02] hover:border-white/[0.06] transition-colors"
                >
                  <span className="text-slate-600 font-mono shrink-0 w-16">
                    {new Date(entry.timestamp * 1000).toLocaleTimeString("en-US", {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                  <span className={cn(
                    "shrink-0 font-medium w-32 truncate",
                    eventColors[entry.event_type] ?? "text-slate-400"
                  )}>
                    {entry.event_type}
                  </span>
                  <span className="text-slate-400 flex-1 truncate">{entry.action}</span>
                </motion.div>
              );
            })}
          </div>
        </div>
      </Card>
    </motion.div>
  );
}
