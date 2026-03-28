"use client";

import React, { useState, useMemo, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { StatCard } from "@/components/ui/stat-card";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import {
  formatCurrency,
  formatPercent,
  formatNumber,
  formatTimeAgo,
  cn,
} from "@/lib/utils";
import { Switch } from "@/components/ui/switch";
import { useScannerOpportunities, useAutoExecution, useSetAutoExecution } from "@/hooks/useApi";
import type { ArbitrageOpportunity, StrategyType } from "@/types";

// ---------------------------------------------------------------------------
// Extended mock display type
// ---------------------------------------------------------------------------

interface OpportunityDisplay extends ArbitrageOpportunity {
  status: "DETECTED" | "EXECUTING" | "EXPIRED" | "REJECTED";
  riskFlags: string[];
  rejectionReason?: string;
  path?: string;
  marketSnapshot?: {
    buyBid: number;
    buyAsk: number;
    sellBid: number;
    sellAsk: number;
  };
  orderbookEstimate?: {
    depth: string;
    vwapBuy: number;
    vwapSell: number;
  };
  feeBreakdown?: {
    buyFee: number;
    sellFee: number;
    transferFee: number;
    slippageEst: number;
  };
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const strategyOptions = [
  { value: "all", label: "全部策略" },
  { value: "spatial", label: "跨交易所" },
  { value: "triangular", label: "三角套利" },
  { value: "funding_rate", label: "期现套利" },
  { value: "statistical", label: "统计套利" },
];

const exchangeOptions = [
  { value: "all", label: "全部交易所" },
  { value: "binance", label: "Binance" },
  { value: "okx", label: "OKX" },
  { value: "bybit", label: "Bybit" },
];

const sortOptions = [
  { value: "profit", label: "按净利润" },
  { value: "spread", label: "按价差" },
  { value: "confidence", label: "按置信度" },
  { value: "time", label: "按时间" },
];

const strategyColors: Record<string, { variant: "success" | "info" | "warning" | "danger" | "neutral"; label: string }> = {
  spatial: { variant: "info", label: "跨交易所" },
  triangular: { variant: "warning", label: "三角套利" },
  funding_rate: { variant: "success", label: "期现套利" },
  statistical: { variant: "neutral", label: "统计套利" },
  cross_exchange: { variant: "info", label: "跨交易所" },
};

const statusColors: Record<string, "success" | "info" | "warning" | "danger" | "neutral"> = {
  DETECTED: "info",
  EXECUTING: "success",
  EXPIRED: "neutral",
  REJECTED: "danger",
};

const statusLabels: Record<string, string> = {
  DETECTED: "已检测",
  EXECUTING: "执行中",
  EXPIRED: "已过期",
  REJECTED: "已拒绝",
};

// ---------------------------------------------------------------------------
// Animation variants
// ---------------------------------------------------------------------------

const stagger = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" as const } },
};

const rowVariant = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: "easeOut" as const } },
  exit: { opacity: 0, x: -12, transition: { duration: 0.2 } },
};

// ---------------------------------------------------------------------------
// Build extended opportunities from raw data
// ---------------------------------------------------------------------------

function buildExtendedOpportunities(raw: ArbitrageOpportunity[]): OpportunityDisplay[] {
  return raw.map((opp, idx) => {
    // Simulate status, risk flags, and extra detail data
    const statuses: OpportunityDisplay["status"][] = ["DETECTED", "DETECTED", "DETECTED", "EXECUTING", "REJECTED", "DETECTED", "EXPIRED", "REJECTED"];
    const riskSets: string[][] = [[], ["低流动性"], [], [], ["高滑点", "频率限制"], ["低置信度"], [], ["最大敞口"]];
    const rejections = [undefined, undefined, undefined, undefined, "扣除手续费后价差低于最低阈值", undefined, undefined, "总敞口将超过风控引擎限额 $200,000"];
    const status = statuses[idx % statuses.length];
    const riskFlags = riskSets[idx % riskSets.length];

    return {
      ...opp,
      status,
      riskFlags,
      rejectionReason: rejections[idx % rejections.length],
      path: opp.type === "triangular"
        ? `${opp.symbol.split("/")[0]}/USDT -> ${opp.symbol} -> ${opp.symbol.split("/")[1]}/USDT`
        : undefined,
      marketSnapshot: {
        buyBid: opp.buyPrice * 0.9999,
        buyAsk: opp.buyPrice,
        sellBid: opp.sellPrice,
        sellAsk: opp.sellPrice * 1.0001,
      },
      orderbookEstimate: {
        depth: formatCurrency(opp.maxVolume * opp.buyPrice * 3, { compact: true }),
        vwapBuy: opp.buyPrice * 1.00005,
        vwapSell: opp.sellPrice * 0.99995,
      },
      feeBreakdown: {
        buyFee: opp.fees * 0.45,
        sellFee: opp.fees * 0.45,
        transferFee: opp.fees * 0.05,
        slippageEst: opp.fees * 0.05,
      },
    };
  });
}

// ---------------------------------------------------------------------------
// Component: Opportunity Detail Drawer
// ---------------------------------------------------------------------------

function OpportunityDrawer({
  opp,
  onClose,
}: {
  opp: OpportunityDisplay;
  onClose: () => void;
}) {
  const strat = strategyColors[opp.type] ?? strategyColors.spatial;
  const [showDebug, setShowDebug] = useState(false);

  return (
    <>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Drawer */}
      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 30, stiffness: 300 }}
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-xl bg-dark-950 border-l border-white/[0.06] overflow-y-auto custom-scrollbar"
      >
        <div className="p-6 space-y-6">
          {/* Header */}
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Badge variant={strat.variant} size="sm">{strat.label}</Badge>
                <Badge variant={statusColors[opp.status] ?? "neutral"} dot size="sm">
                  {statusLabels[opp.status] ?? opp.status}
                </Badge>
              </div>
              <h2 className="text-xl font-semibold text-white">{opp.symbol}</h2>
              <div className="flex items-center gap-1.5 text-sm text-slate-400 mt-1">
                <span className="capitalize font-medium text-slate-300">{opp.buyExchange}</span>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-primary-400">
                  <path d="M2 8h12M10 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="capitalize font-medium text-slate-300">{opp.sellExchange}</span>
              </div>
              {opp.path && (
                <p className="text-xs text-slate-500 mt-1">路径: {opp.path}</p>
              )}
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-dark-800 transition-colors text-slate-400 hover:text-slate-200"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M6 6l8 8M14 6l-8 8" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          {/* Profit Summary */}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-dark-900 border border-white/[0.06] p-4">
              <p className="text-[10px] text-slate-600 uppercase tracking-wider">理论利润</p>
              <p className="text-lg font-semibold font-mono text-slate-200 mt-1">
                {formatPercent(opp.estimatedProfitPercent, { decimals: 4 })}
              </p>
              <p className="text-xs font-mono text-slate-500">{formatCurrency(opp.estimatedProfit)}</p>
            </div>
            <div className="rounded-xl bg-dark-900 border border-success-500/20 p-4">
              <p className="text-[10px] text-slate-600 uppercase tracking-wider">预估净利润</p>
              <p className="text-lg font-semibold font-mono text-success-400 mt-1">
                {formatPercent(opp.netProfitPercent * 100, { decimals: 3 })}
              </p>
              <p className="text-xs font-mono text-success-500">{formatCurrency(opp.netProfit)}</p>
            </div>
          </div>

          {/* Market Snapshot */}
          {opp.marketSnapshot && (
            <div className="rounded-xl bg-dark-900 border border-white/[0.06] p-4">
              <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">市场快照</h3>
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">{opp.buyExchange.toUpperCase()} Bid / Ask</span>
                  <span className="font-mono text-slate-300">
                    {formatCurrency(opp.marketSnapshot.buyBid)} / {formatCurrency(opp.marketSnapshot.buyAsk)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">{opp.sellExchange.toUpperCase()} Bid / Ask</span>
                  <span className="font-mono text-slate-300">
                    {formatCurrency(opp.marketSnapshot.sellBid)} / {formatCurrency(opp.marketSnapshot.sellAsk)}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Orderbook Estimate */}
          {opp.orderbookEstimate && (
            <div className="rounded-xl bg-dark-900 border border-white/[0.06] p-4">
              <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">订单簿估算</h3>
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">可用深度</span>
                  <span className="font-mono text-slate-300">{opp.orderbookEstimate.depth}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">VWAP 买入价</span>
                  <span className="font-mono text-slate-300">{formatCurrency(opp.orderbookEstimate.vwapBuy)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">VWAP 卖出价</span>
                  <span className="font-mono text-slate-300">{formatCurrency(opp.orderbookEstimate.vwapSell)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Fee / Slippage Breakdown */}
          {opp.feeBreakdown && (
            <div className="rounded-xl bg-dark-900 border border-white/[0.06] p-4">
              <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">费用 / 滑点明细</h3>
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">买入手续费</span>
                  <span className="font-mono text-slate-300">{formatCurrency(opp.feeBreakdown.buyFee)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">卖出手续费</span>
                  <span className="font-mono text-slate-300">{formatCurrency(opp.feeBreakdown.sellFee)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">划转费用</span>
                  <span className="font-mono text-slate-300">{formatCurrency(opp.feeBreakdown.transferFee)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">预估滑点</span>
                  <span className="font-mono text-warning-400">{formatCurrency(opp.feeBreakdown.slippageEst)}</span>
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-white/[0.04]">
                  <span className="text-slate-400 font-medium">总费用</span>
                  <span className="font-mono text-slate-200">{formatCurrency(opp.fees)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Risk Flags */}
          {opp.riskFlags.length > 0 && (
            <div className="rounded-xl bg-dark-900 border border-danger-500/20 p-4">
              <h3 className="text-xs font-medium text-danger-400 uppercase tracking-wider mb-3">风险标签</h3>
              <div className="flex flex-wrap gap-2">
                {opp.riskFlags.map((flag) => (
                  <Badge key={flag} variant="danger" size="sm">{flag}</Badge>
                ))}
              </div>
              {opp.rejectionReason && (
                <p className="text-xs text-danger-400 mt-3 pt-2 border-t border-danger-500/20">
                  {opp.rejectionReason}
                </p>
              )}
            </div>
          )}

          {/* Debug Details (collapsible) */}
          <div className="rounded-xl bg-dark-900 border border-white/[0.06] overflow-hidden">
            <button
              onClick={() => setShowDebug(!showDebug)}
              className="w-full flex items-center justify-between p-4 hover:bg-dark-800/50 transition-colors"
            >
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">调试信息</span>
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                className={cn(
                  "text-slate-500 transition-transform duration-200",
                  showDebug && "rotate-180"
                )}
              >
                <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <AnimatePresence>
              {showDebug && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="px-4 pb-4 space-y-1.5 text-[11px] font-mono">
                    <div className="flex justify-between"><span className="text-slate-600">id</span><span className="text-slate-400">{opp.id}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">type</span><span className="text-slate-400">{opp.type}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">buyPrice</span><span className="text-slate-400">{opp.buyPrice}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">sellPrice</span><span className="text-slate-400">{opp.sellPrice}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">spreadAbsolute</span><span className="text-slate-400">{opp.spreadAbsolute}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">spreadPercent</span><span className="text-slate-400">{opp.spreadPercent}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">maxVolume</span><span className="text-slate-400">{opp.maxVolume}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">fees</span><span className="text-slate-400">{opp.fees}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">confidence</span><span className="text-slate-400">{opp.confidence}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">ttl</span><span className="text-slate-400">{opp.ttl}ms</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">detectedAt</span><span className="text-slate-400">{opp.detectedAt}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">expiresAt</span><span className="text-slate-400">{opp.expiresAt}</span></div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-3 pt-2">
            <Button
              variant="secondary"
              size="sm"
              className="flex-1"
            >
              模拟执行
            </Button>
            {opp.status === "DETECTED" && (
              <Button
                size="sm"
                className="flex-1 bg-success-600 hover:bg-success-500 shadow-lg shadow-success-600/20 text-white"
              >
                创建执行计划
              </Button>
            )}
          </div>
        </div>
      </motion.div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Component: Opportunity Table Row
// ---------------------------------------------------------------------------

function OpportunityRow({
  opp,
  index,
  onSelect,
}: {
  opp: OpportunityDisplay;
  index: number;
  onSelect: (opp: OpportunityDisplay) => void;
}) {
  const strat = strategyColors[opp.type] ?? strategyColors.spatial;
  const statusVariant = statusColors[opp.status] ?? "neutral";
  const isExecutable = opp.status === "DETECTED";
  const isRejected = opp.status === "REJECTED";
  const executableValue = opp.maxVolume * opp.buyPrice;

  const spreadIntensity = Math.min(1, opp.spreadPercent / 0.15);
  const spreadColor =
    spreadIntensity > 0.6 ? "text-success-300" :
    spreadIntensity > 0.3 ? "text-success-400" : "text-success-500";

  return (
    <motion.div
      layout
      variants={rowVariant}
      initial="hidden"
      animate="show"
      exit="exit"
      transition={{ delay: index * 0.03 }}
      onClick={() => onSelect(opp)}
      className={cn(
        "rounded-xl border bg-dark-900 p-4 cursor-pointer transition-all duration-300",
        isExecutable
          ? "border-white/[0.06] hover:border-success-500/30 hover:bg-dark-900/80"
          : isRejected
            ? "border-danger-500/10 hover:border-danger-500/20"
            : "border-white/[0.06] hover:border-white/[0.1]"
      )}
    >
      {/* Row 1: badges + time */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Badge variant={strat.variant} size="sm">{strat.label}</Badge>
          <Badge variant={statusVariant} dot size="sm">
            {statusLabels[opp.status] ?? opp.status}
          </Badge>
        </div>
        <span className="text-[10px] text-slate-600 font-mono">
          {formatTimeAgo(opp.detectedAt)}
        </span>
      </div>

      {/* Row 2: symbol + exchange route */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-lg font-semibold text-white">{opp.symbol}</h3>
          {opp.path && <p className="text-[10px] text-slate-500 mt-0.5">{opp.path}</p>}
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <span className="capitalize font-medium text-slate-300">{opp.buyExchange}</span>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-primary-400">
            <path d="M2 7h10M8 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="capitalize font-medium text-slate-300">{opp.sellExchange}</span>
        </div>
      </div>

      {/* Row 3: metrics grid */}
      <div className="grid grid-cols-4 gap-x-3 gap-y-2 mb-3">
        <div>
          <p className="text-[10px] text-slate-600 uppercase tracking-wider">理论利润%</p>
          <p className={cn("text-sm font-semibold font-mono", spreadColor)}>
            {formatPercent(opp.spreadPercent, { decimals: 4 })}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-600 uppercase tracking-wider">预估净利润%</p>
          <p className="text-sm font-semibold font-mono text-success-400">
            {formatPercent(opp.netProfitPercent * 100, { decimals: 3 })}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-600 uppercase tracking-wider">可执行价值</p>
          <p className="text-sm font-mono text-slate-300">
            {formatCurrency(executableValue, { compact: true })}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-600 uppercase tracking-wider">净利润</p>
          <p className="text-sm font-semibold font-mono text-success-400">
            {formatCurrency(opp.netProfit)}
          </p>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
          <span className="uppercase tracking-wider">置信度</span>
          <span className="font-mono">{(opp.confidence * 100).toFixed(0)}%</span>
        </div>
        <Progress
          value={opp.confidence * 100}
          size="sm"
          variant={
            opp.confidence >= 0.85 ? "success" :
            opp.confidence >= 0.7 ? "accent" :
            opp.confidence >= 0.5 ? "warning" : "danger"
          }
        />
      </div>

      {/* Risk flags + rejection */}
      {opp.riskFlags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {opp.riskFlags.map((flag) => (
            <Badge key={flag} variant="danger" size="sm">{flag}</Badge>
          ))}
        </div>
      )}
      {isRejected && opp.rejectionReason && (
        <div className="rounded-lg bg-danger-500/10 border border-danger-500/20 px-3 py-2 mb-3">
          <p className="text-xs text-danger-400">{opp.rejectionReason}</p>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        {isExecutable && (
          <Button
            size="sm"
            className="flex-1 bg-success-600 hover:bg-success-500 shadow-lg shadow-success-600/20 text-white"
            onClick={(e: React.MouseEvent) => { e.stopPropagation(); }}
          >
            执行
          </Button>
        )}
        <Button
          variant="secondary"
          size="sm"
          className={cn(!isExecutable && "flex-1")}
          onClick={(e: React.MouseEvent) => { e.stopPropagation(); }}
        >
          模拟
        </Button>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function OpportunitiesPage() {
  // Filter state
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [exchangeFilter, setExchangeFilter] = useState("all");
  const [minProfit, setMinProfit] = useState("");
  const [sortBy, setSortBy] = useState("profit");
  const [selectedOpp, setSelectedOpp] = useState<OpportunityDisplay | null>(null);

  // Auto-execution state
  const { data: autoExecStatus } = useAutoExecution();
  const setAutoExec = useSetAutoExecution();
  const [tradeSizeInput, setTradeSizeInput] = useState("");
  const [tradeSizeSaved, setTradeSizeSaved] = useState(false);

  // Sync trade size input from API
  useEffect(() => {
    if (autoExecStatus?.trade_size_usdt && !tradeSizeInput) {
      setTradeSizeInput(String(autoExecStatus.trade_size_usdt));
    }
  }, [autoExecStatus?.trade_size_usdt]);

  const handleAutoExecToggle = useCallback((enabled: boolean) => {
    setAutoExec.mutate({ enabled });
  }, [setAutoExec]);

  const handleTradeSizeSave = useCallback(() => {
    const val = parseFloat(tradeSizeInput);
    if (!isNaN(val) && val > 0) {
      setAutoExec.mutate({ trade_size_usdt: val }, {
        onSuccess: () => {
          setTradeSizeSaved(true);
          setTimeout(() => setTradeSizeSaved(false), 2000);
        },
      });
    }
  }, [tradeSizeInput, setAutoExec]);

  // Auto-refresh countdown
  const [refreshCountdown, setRefreshCountdown] = useState(5);
  useEffect(() => {
    const interval = setInterval(() => {
      setRefreshCountdown((prev) => (prev <= 1 ? 5 : prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Fetch data via hook
  const { data: rawOpportunities = [] } = useScannerOpportunities();

  // Build extended display data
  const extendedOpportunities = useMemo(
    () => buildExtendedOpportunities(rawOpportunities),
    [rawOpportunities]
  );

  // Computed stats
  const activeCount = useMemo(
    () => extendedOpportunities.filter((o) => o.status === "DETECTED" || o.status === "EXECUTING").length,
    [extendedOpportunities]
  );

  const avgSpread = useMemo(() => {
    if (extendedOpportunities.length === 0) return 0;
    return extendedOpportunities.reduce((sum, o) => sum + o.spreadPercent, 0) / extendedOpportunities.length;
  }, [extendedOpportunities]);

  const bestOpp = useMemo(
    () => extendedOpportunities.reduce(
      (best, o) => (o.netProfitPercent > best.netProfitPercent ? o : best),
      extendedOpportunities[0] ?? { netProfitPercent: 0, symbol: "--" } as OpportunityDisplay
    ),
    [extendedOpportunities]
  );

  const blockedCount = useMemo(
    () => extendedOpportunities.filter((o) => o.status === "REJECTED").length,
    [extendedOpportunities]
  );

  // Filtered & sorted
  const filtered = useMemo(() => {
    let result = [...extendedOpportunities];
    if (strategyFilter !== "all") result = result.filter((o) => o.type === strategyFilter);
    if (exchangeFilter !== "all") result = result.filter((o) => o.buyExchange === exchangeFilter || o.sellExchange === exchangeFilter);
    if (minProfit) {
      const min = parseFloat(minProfit);
      if (!isNaN(min)) result = result.filter((o) => o.netProfitPercent * 100 >= min);
    }
    result.sort((a, b) => {
      switch (sortBy) {
        case "profit": return b.netProfit - a.netProfit;
        case "spread": return b.spreadPercent - a.spreadPercent;
        case "confidence": return b.confidence - a.confidence;
        case "time": return new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime();
        default: return 0;
      }
    });
    return result;
  }, [extendedOpportunities, strategyFilter, exchangeFilter, minProfit, sortBy]);

  const handleSelectOpp = useCallback((opp: OpportunityDisplay) => {
    setSelectedOpp(opp);
  }, []);

  const handleCloseDrawer = useCallback(() => {
    setSelectedOpp(null);
  }, []);

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
      <motion.div variants={fadeUp} className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">套利机会</h1>
          <p className="text-sm text-slate-500 mt-0.5">跨交易所实时套利机会监控</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success-400 opacity-40" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-success-400" />
            </span>
            自动刷新 {refreshCountdown}秒
          </div>
        </div>
      </motion.div>

      {/* ================================================================= */}
      {/* Auto-execution Controls                                           */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp}>
        <Card padding="sm">
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-3">
              <Switch
                checked={autoExecStatus?.enabled ?? false}
                onChange={handleAutoExecToggle}
                size="sm"
              />
              <div>
                <span className="text-sm font-medium text-slate-200">自动执行</span>
                <p className="text-[10px] text-slate-500">
                  {autoExecStatus?.enabled ? "检测到机会后自动执行" : "需要手动点击执行"}
                </p>
              </div>
            </div>
            <div className="h-8 w-px bg-white/[0.06] hidden sm:block" />
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400 whitespace-nowrap">起始金额</label>
              <div className="relative w-36">
                <input
                  type="number"
                  value={tradeSizeInput}
                  onChange={(e) => setTradeSizeInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleTradeSizeSave(); }}
                  className="w-full rounded-lg bg-dark-800 border border-white/[0.08] px-3 py-1.5 text-sm font-mono text-slate-200 placeholder-slate-600 focus:border-primary-500/40 focus:outline-none"
                  placeholder="1000"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-slate-500">USDT</span>
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={handleTradeSizeSave}
                disabled={setAutoExec.isPending}
              >
                {tradeSizeSaved ? "已保存" : "保存"}
              </Button>
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <Badge variant={autoExecStatus?.enabled ? "success" : "neutral"} dot size="sm">
                {autoExecStatus?.enabled ? "自动" : "手动"}
              </Badge>
              <Badge variant="info" size="sm">
                {autoExecStatus?.trading_mode === "live" ? "实盘" : "模拟"}
              </Badge>
            </div>
          </div>
        </Card>
      </motion.div>

      {/* ================================================================= */}
      {/* Stat Cards                                                        */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp} className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="活跃机会"
          value={activeCount}
          icon={
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="10" cy="10" r="7" />
              <path d="M10 6v4l3 2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
        />
        <StatCard
          label="平均价差"
          value={formatPercent(avgSpread, { decimals: 4 })}
          icon={
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 15l4-4 3 3 4-5 5 4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
        />
        <StatCard
          label="最佳机会"
          value={bestOpp ? `${formatPercent(bestOpp.netProfitPercent * 100)} (${bestOpp.symbol})` : "--"}
          icon={
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M10 2l2.5 5 5.5.8-4 3.9.9 5.5L10 14.7 5.1 17.2l.9-5.5-4-3.9 5.5-.8L10 2z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
        />
        <StatCard
          label="风控拦截"
          value={blockedCount}
          icon={
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M10 2a8 8 0 100 16 8 8 0 000-16z" />
              <path d="M13 7l-6 6M7 7l6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
        />
      </motion.div>

      {/* ================================================================= */}
      {/* Filter Bar                                                        */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp}>
        <Card padding="sm">
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-44">
              <Select
                label="策略类型"
                options={strategyOptions}
                value={strategyFilter}
                onChange={(e) => setStrategyFilter(e.target.value)}
              />
            </div>
            <div className="w-40">
              <Select
                label="交易所"
                options={exchangeOptions}
                value={exchangeFilter}
                onChange={(e) => setExchangeFilter(e.target.value)}
              />
            </div>
            <div className="w-36">
              <Input
                label="最低利润%"
                placeholder="0.01"
                type="number"
                step="0.001"
                value={minProfit}
                onChange={(e) => setMinProfit(e.target.value)}
              />
            </div>
            <div className="w-40">
              <Select
                label="排序"
                options={sortOptions}
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
              />
            </div>
            <div className="flex items-center h-9 ml-auto">
              <Badge variant="info" size="sm">
                {filtered.length} / {extendedOpportunities.length} 条
              </Badge>
            </div>
          </div>
        </Card>
      </motion.div>

      {/* ================================================================= */}
      {/* Opportunity Cards Grid                                            */}
      {/* ================================================================= */}
      <motion.div variants={fadeUp}>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <AnimatePresence mode="popLayout">
            {filtered.map((opp, idx) => (
              <OpportunityRow
                key={opp.id}
                opp={opp}
                index={idx}
                onSelect={handleSelectOpp}
              />
            ))}
          </AnimatePresence>
        </div>
        {filtered.length === 0 && (
          <div className="flex items-center justify-center py-16 text-slate-600 text-sm">
            没有符合筛选条件的机会
          </div>
        )}
      </motion.div>

      {/* ================================================================= */}
      {/* Detail Drawer                                                     */}
      {/* ================================================================= */}
      <AnimatePresence>
        {selectedOpp && (
          <OpportunityDrawer opp={selectedOpp} onClose={handleCloseDrawer} />
        )}
      </AnimatePresence>
    </motion.div>
  );
}
