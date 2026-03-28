"use client";

import React, { useState, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Tabs, TabPanel } from "@/components/ui/tabs";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { StatusDot } from "@/components/ui/status-dot";
import { Progress } from "@/components/ui/progress";
import { cn, formatDuration, formatCurrency } from "@/lib/utils";
import {
  useStrategies,
  useRiskRules,
  useSystemHealth,
  useExchanges,
  useSystemMetrics,
} from "@/hooks/useApi";
import {
  mockStrategies,
  mockRiskRules,
  mockExchanges,
  mockSystemHealth,
  mockSystemMetrics,
} from "@/lib/mock-data";
import type { StrategyConfig, RiskRule, TradingMode } from "@/types";

// ---------------------------------------------------------------------------
// Settings tabs
// ---------------------------------------------------------------------------

const settingsTabs = [
  { id: "general", label: "常规设置" },
  { id: "strategies", label: "策略配置" },
  { id: "risk", label: "风控规则" },
  { id: "alerts", label: "告警设置" },
  { id: "system", label: "系统信息" },
];

// ---------------------------------------------------------------------------
// Saved state toast
// ---------------------------------------------------------------------------

function SaveToast({ show, message }: { show: boolean; message: string }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg bg-success-600 px-4 py-2.5 text-sm font-medium text-white shadow-lg"
        >
          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
          {message}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------------------
// Change tracking indicator
// ---------------------------------------------------------------------------

function UnsavedBanner({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      className="rounded-lg bg-warning-600/10 border border-warning-500/30 px-4 py-2 flex items-center gap-2 text-xs text-warning-300"
    >
      <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
      </svg>
      未保存更改 - 请点击保存按钮保存您的修改
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Tab 1: 常规设置
// ---------------------------------------------------------------------------

function GeneralTab() {
  const [tradingMode, setTradingMode] = useState<TradingMode>("paper");
  const [showLiveWarning, setShowLiveWarning] = useState(false);
  const [executionTimeout, setExecutionTimeout] = useState("30");
  const [scanInterval, setScanInterval] = useState("2000");
  const [orderbookDepth, setOrderbookDepth] = useState("20");
  const [opportunityTtl, setOpportunityTtl] = useState("5");
  const [saved, setSaved] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  const handleModeToggle = useCallback(() => {
    if (tradingMode === "paper") {
      setShowLiveWarning(true);
    } else {
      setTradingMode("paper");
      setShowLiveWarning(false);
      setHasChanges(true);
    }
  }, [tradingMode]);

  const confirmLiveMode = useCallback(() => {
    setTradingMode("live");
    setShowLiveWarning(false);
    setHasChanges(true);
  }, []);

  const handleSave = useCallback(() => {
    setSaved(true);
    setHasChanges(false);
    setTimeout(() => setSaved(false), 2000);
  }, []);

  const markChanged = useCallback(() => setHasChanges(true), []);

  return (
    <div className="space-y-6">
      <UnsavedBanner show={hasChanges} />

      {/* Trading Mode */}
      <Card>
        <CardHeader>交易模式</CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-200 font-medium">
                当前模式:{" "}
                <Badge
                  variant={tradingMode === "live" ? "danger" : "info"}
                  size="md"
                  dot
                >
                  {tradingMode === "live" ? "实盘 (Live)" : "模拟 (Paper)"}
                </Badge>
              </p>
              <p className="text-xs text-slate-500 mt-1">
                {tradingMode === "live"
                  ? "将在交易所下达真实订单，请谨慎操作。"
                  : "模拟交易模式，不会下达真实订单。"}
              </p>
            </div>
            <Switch
              checked={tradingMode === "live"}
              onChange={handleModeToggle}
              label={tradingMode === "live" ? "实盘" : "模拟"}
            />
          </div>

          {/* Live mode warning */}
          <AnimatePresence>
            {showLiveWarning && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-4 rounded-lg bg-danger-600/10 border border-danger-500/30 p-4"
              >
                <div className="flex items-start gap-3">
                  <svg className="h-5 w-5 text-danger-400 mt-0.5 shrink-0" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  <div className="flex-1">
                    <h4 className="text-sm font-semibold text-danger-300">
                      警告：即将切换至实盘模式
                    </h4>
                    <p className="text-xs text-slate-400 mt-1">
                      这将在所有已连接的交易所启用真实订单执行，将使用真实资金。
                      请确保所有风控规则已正确配置后再继续操作。
                    </p>
                    <div className="flex items-center gap-2 mt-3">
                      <Button variant="danger" size="sm" onClick={confirmLiveMode}>
                        确认切换实盘
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setShowLiveWarning(false)}>
                        取消
                      </Button>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Live mode banner */}
          {tradingMode === "live" && !showLiveWarning && (
            <div className="mt-4 rounded-lg bg-danger-600/10 border border-danger-500/30 p-3 flex items-center gap-2">
              <svg className="h-4 w-4 text-danger-400 shrink-0" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <span className="text-xs text-danger-300 font-medium">
                实盘模式已启用 - 所有执行将使用真实资金
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Execution Parameters */}
      <Card>
        <CardHeader>执行参数</CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <Input
              label="执行超时(秒)"
              type="number"
              value={executionTimeout}
              onChange={(e) => { setExecutionTimeout(e.target.value); markChanged(); }}
              suffix="秒"
            />
            <Input
              label="扫描间隔(毫秒)"
              type="number"
              value={scanInterval}
              onChange={(e) => { setScanInterval(e.target.value); markChanged(); }}
              suffix="ms"
            />
            <Input
              label="订单簿深度"
              type="number"
              value={orderbookDepth}
              onChange={(e) => { setOrderbookDepth(e.target.value); markChanged(); }}
              suffix="档"
            />
            <Input
              label="机会过期时间(秒)"
              type="number"
              value={opportunityTtl}
              onChange={(e) => { setOpportunityTtl(e.target.value); markChanged(); }}
              suffix="秒"
            />
          </div>
          <div className="flex justify-end mt-6">
            <Button onClick={handleSave} disabled={!hasChanges}>
              保存设置
            </Button>
          </div>
        </CardContent>
      </Card>

      <SaveToast show={saved} message="常规设置已保存" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 2: 策略配置
// ---------------------------------------------------------------------------

function StrategiesTab() {
  const { data: apiStrategies } = useStrategies();
  const [strategies, setStrategies] = useState<StrategyConfig[]>(mockStrategies);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [dirtyIds, setDirtyIds] = useState<Set<string>>(new Set());

  // Sync from API when available
  useMemo(() => {
    if (apiStrategies && apiStrategies.length > 0) {
      setStrategies(apiStrategies);
    }
  }, [apiStrategies]);

  const updateStrategy = useCallback((id: string, partial: Partial<StrategyConfig>) => {
    setStrategies((prev) =>
      prev.map((s) => (s.id === id ? { ...s, ...partial } : s))
    );
    setDirtyIds((prev) => new Set(prev).add(id));
  }, []);

  const handleSave = useCallback((id: string) => {
    setSavedId(id);
    setDirtyIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    setTimeout(() => setSavedId(null), 2000);
  }, []);

  const allExchanges = [
    { value: "binance", label: "Binance" },
    { value: "okx", label: "OKX" },
    { value: "bybit", label: "Bybit" },
    { value: "kraken", label: "Kraken" },
    { value: "coinbase", label: "Coinbase" },
  ];

  return (
    <div className="space-y-4">
      {strategies.map((strategy) => (
        <Card key={strategy.id} hover>
          <CardContent>
            {/* Strategy header */}
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-white">{strategy.name}</h3>
                  <Badge
                    variant={
                      strategy.type === "spatial" ? "info" :
                      strategy.type === "triangular" ? "success" :
                      strategy.type === "funding_rate" ? "warning" : "neutral"
                    }
                    size="sm"
                  >
                    {strategy.type}
                  </Badge>
                  {dirtyIds.has(strategy.id) && (
                    <span className="text-[10px] text-warning-400 font-medium">已修改</span>
                  )}
                  {savedId === strategy.id && (
                    <motion.span
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0 }}
                      className="text-xs text-success-400 font-medium"
                    >
                      已保存
                    </motion.span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-1 max-w-lg">{strategy.description}</p>
              </div>
              <Switch
                checked={strategy.enabled}
                onChange={(enabled) => updateStrategy(strategy.id, { enabled })}
                size="sm"
              />
            </div>

            {/* Stats row */}
            <div className="flex items-center gap-4 mb-4 text-xs">
              <div className="flex items-center gap-1.5 text-slate-400">
                <span className="text-slate-500">交易数:</span>
                <span className="font-number text-slate-300">{strategy.stats.totalTrades.toLocaleString()}</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-400">
                <span className="text-slate-500">胜率:</span>
                <span className="font-number text-success-400">{strategy.stats.winRate}%</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-400">
                <span className="text-slate-500">盈亏:</span>
                <span className="font-number text-success-400">{formatCurrency(strategy.stats.totalPnl)}</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-400">
                <span className="text-slate-500">平均执行:</span>
                <span className="font-number text-slate-300">{strategy.stats.avgExecutionTime}ms</span>
              </div>
            </div>

            {/* Config fields */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Exchanges multi-select */}
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">交易所</label>
                <div className="flex flex-wrap gap-1.5">
                  {allExchanges.map((ex) => {
                    const active = strategy.exchanges.includes(ex.value as typeof strategy.exchanges[number]);
                    return (
                      <button
                        key={ex.value}
                        onClick={() => {
                          const next = active
                            ? strategy.exchanges.filter((e) => e !== ex.value)
                            : [...strategy.exchanges, ex.value as typeof strategy.exchanges[number]];
                          updateStrategy(strategy.id, { exchanges: next });
                        }}
                        className={cn(
                          "px-2 py-1 text-[11px] rounded-md border transition-all duration-150",
                          active
                            ? "bg-primary-600/20 border-primary-500/30 text-primary-300"
                            : "bg-dark-800 border-white/[0.06] text-slate-500 hover:text-slate-300"
                        )}
                      >
                        {ex.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Symbols tags */}
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">交易对</label>
                <div className="flex flex-wrap gap-1">
                  {strategy.symbols.map((sym) => (
                    <span
                      key={sym}
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-dark-700 text-slate-300 border border-white/[0.06]"
                    >
                      {sym}
                      <button
                        onClick={() => {
                          updateStrategy(strategy.id, {
                            symbols: strategy.symbols.filter((s) => s !== sym),
                          });
                        }}
                        className="text-slate-500 hover:text-slate-300 ml-0.5"
                      >
                        x
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              {/* Min Profit Threshold */}
              <Input
                label="最低利润阈值 (%)"
                type="number"
                step="0.01"
                value={String(strategy.minProfitPercent)}
                onChange={(e) =>
                  updateStrategy(strategy.id, {
                    minProfitPercent: parseFloat(e.target.value) || 0,
                  })
                }
                suffix="%"
              />

              {/* Max Order Value */}
              <Input
                label="最大订单金额"
                type="number"
                value={String(strategy.maxPositionSize)}
                onChange={(e) =>
                  updateStrategy(strategy.id, {
                    maxPositionSize: parseFloat(e.target.value) || 0,
                  })
                }
                suffix="USD"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-3">
              <Input
                label="扫描间隔"
                type="number"
                value={String(strategy.cooldownMs)}
                onChange={(e) =>
                  updateStrategy(strategy.id, {
                    cooldownMs: parseInt(e.target.value) || 0,
                  })
                }
                suffix="ms"
              />
              <Input
                label="每日交易限额"
                type="number"
                value={String(strategy.maxDailyTrades)}
                onChange={(e) =>
                  updateStrategy(strategy.id, {
                    maxDailyTrades: parseInt(e.target.value) || 0,
                  })
                }
              />
              {/* Placeholder */}
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">黑名单交易对</label>
                <div className="flex items-center gap-1 h-[38px] px-2 rounded-lg bg-dark-800 border border-white/[0.08] text-xs text-slate-500">
                  <span>未配置</span>
                </div>
              </div>
              <div className="flex items-end">
                <Button
                  size="sm"
                  onClick={() => handleSave(strategy.id)}
                  className="w-full"
                  disabled={!dirtyIds.has(strategy.id)}
                >
                  保存策略
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 3: 风控规则
// ---------------------------------------------------------------------------

const ruleCategories: Record<string, string[]> = {
  "仓位限制": ["max_position_size", "max_exposure"],
  "亏损保护": ["max_daily_loss", "max_drawdown"],
  "执行控制": ["max_slippage", "rate_limit", "circuit_breaker"],
  "余额监控": ["min_balance"],
};

const categoryBadgeVariant: Record<string, "info" | "danger" | "warning" | "neutral"> = {
  "仓位限制": "info",
  "亏损保护": "danger",
  "执行控制": "warning",
  "余额监控": "neutral",
};

function RiskRulesTab() {
  const { data: apiRules } = useRiskRules();
  const [rules, setRules] = useState<RiskRule[]>(mockRiskRules);
  const [saved, setSaved] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [saving, setSaving] = useState(false);

  useMemo(() => {
    if (apiRules && apiRules.length > 0) {
      setRules(apiRules);
    }
  }, [apiRules]);

  const updateRule = useCallback((id: string, partial: Partial<RiskRule>) => {
    setRules((prev) =>
      prev.map((r) => (r.id === id ? { ...r, ...partial } : r))
    );
    setHasChanges(true);
  }, []);

  const handleSaveAll = useCallback(() => {
    setSaving(true);
    setTimeout(() => {
      setSaving(false);
      setSaved(true);
      setHasChanges(false);
      setTimeout(() => setSaved(false), 2000);
    }, 800);
  }, []);

  // Find which category a rule belongs to
  const getCategoryForRule = (ruleType: string): string => {
    for (const [cat, types] of Object.entries(ruleCategories)) {
      if (types.includes(ruleType)) return cat;
    }
    return "其他";
  };

  return (
    <div className="space-y-6">
      <UnsavedBanner show={hasChanges} />

      {Object.entries(ruleCategories).map(([category, types]) => {
        const categoryRules = rules.filter((r) => types.includes(r.type));
        if (categoryRules.length === 0) return null;

        return (
          <div key={category}>
            <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <Badge variant={categoryBadgeVariant[category] ?? "neutral"} size="sm">
                {category}
              </Badge>
              <span className="text-xs text-slate-600 font-normal">
                ({categoryRules.length} 条规则)
              </span>
            </h3>
            <div className="space-y-3">
              {categoryRules.map((rule) => {
                const utilization = rule.threshold > 0 ? (rule.currentValue / rule.threshold) * 100 : 0;
                const isHigh = utilization > 80;
                const isMedium = utilization > 50;

                return (
                  <Card key={rule.id} padding="sm">
                    <CardContent>
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h4 className="text-sm font-medium text-slate-200">{rule.name}</h4>
                            <Badge
                              variant={
                                rule.action === "halt" ? "danger" :
                                rule.action === "block" ? "warning" :
                                rule.action === "reduce" ? "info" : "neutral"
                              }
                              size="sm"
                            >
                              {rule.action}
                            </Badge>
                          </div>
                          <p className="text-xs text-slate-500 mb-3">{rule.description}</p>

                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            <Input
                              label="阈值"
                              type="number"
                              value={String(rule.threshold)}
                              onChange={(e) =>
                                updateRule(rule.id, {
                                  threshold: parseFloat(e.target.value) || 0,
                                })
                              }
                              suffix={rule.unit}
                            />
                            <div>
                              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                                当前值
                              </label>
                              <div className="flex items-center gap-2 h-[38px]">
                                <span className={cn(
                                  "text-sm font-number",
                                  isHigh ? "text-danger-400" : isMedium ? "text-warning-400" : "text-success-400"
                                )}>
                                  {rule.currentValue.toLocaleString()} {rule.unit}
                                </span>
                              </div>
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                                使用率
                              </label>
                              <div className="flex items-center gap-2 h-[38px]">
                                <Progress
                                  value={utilization}
                                  variant={isHigh ? "danger" : isMedium ? "warning" : "success"}
                                  size="sm"
                                  className="flex-1"
                                />
                                <span className="text-xs font-number text-slate-400 w-10 text-right">
                                  {utilization.toFixed(0)}%
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                        <Switch
                          checked={rule.enabled}
                          onChange={(enabled) => updateRule(rule.id, { enabled })}
                          size="sm"
                        />
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        );
      })}

      <div className="flex justify-end">
        <Button onClick={handleSaveAll} loading={saving} disabled={!hasChanges}>
          保存全部规则
        </Button>
      </div>

      <SaveToast show={saved} message="风控规则已保存" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 4: 告警设置
// ---------------------------------------------------------------------------

function AlertsTab() {
  const [alertCheckInterval, setAlertCheckInterval] = useState("30");
  const [webNotifications, setWebNotifications] = useState(true);
  const [logOutput, setLogOutput] = useState(true);
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPass, setSmtpPass] = useState("");
  const [emailTo, setEmailTo] = useState("");
  const [severityThreshold, setSeverityThreshold] = useState("warning");
  const [saved, setSaved] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [saving, setSaving] = useState(false);

  const markChanged = useCallback(() => setHasChanges(true), []);

  const handleSave = useCallback(() => {
    setSaving(true);
    setTimeout(() => {
      setSaving(false);
      setSaved(true);
      setHasChanges(false);
      setTimeout(() => setSaved(false), 2000);
    }, 800);
  }, []);

  return (
    <div className="space-y-4">
      <UnsavedBanner show={hasChanges} />

      {/* Alert Check Interval */}
      <Card>
        <CardHeader>告警检查间隔</CardHeader>
        <CardContent>
          <div className="max-w-xs">
            <Input
              label="检查间隔"
              type="number"
              value={alertCheckInterval}
              onChange={(e) => { setAlertCheckInterval(e.target.value); markChanged(); }}
              suffix="秒"
            />
          </div>
          <p className="text-xs text-slate-500 mt-2">
            系统每隔此间隔检查一次告警条件。
          </p>
        </CardContent>
      </Card>

      {/* Severity Threshold */}
      <Card>
        <CardHeader>告警严重程度阈值</CardHeader>
        <CardContent>
          <p className="text-xs text-slate-500 mb-3">
            仅达到或超过所选严重程度的告警才会触发通知。
          </p>
          <div className="flex items-center gap-2">
            {([
              { id: "info", label: "信息", color: "primary" },
              { id: "warning", label: "警告", color: "warning" },
              { id: "error", label: "错误", color: "danger" },
              { id: "critical", label: "严重", color: "danger" },
            ] as const).map((sev) => (
              <button
                key={sev.id}
                onClick={() => { setSeverityThreshold(sev.id); markChanged(); }}
                className={cn(
                  "px-3 py-1.5 text-xs font-medium rounded-lg border transition-all duration-200",
                  severityThreshold === sev.id
                    ? sev.id === "critical" || sev.id === "error"
                      ? "bg-danger-600/20 border-danger-500/40 text-danger-300"
                      : sev.id === "warning"
                        ? "bg-warning-600/20 border-warning-500/40 text-warning-300"
                        : "bg-primary-600/20 border-primary-500/40 text-primary-300"
                    : "bg-dark-800 border-white/[0.06] text-slate-500 hover:text-slate-300"
                )}
              >
                {sev.label}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Notification Channels */}
      <Card>
        <CardHeader>通知渠道</CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Log Output */}
            <div className="flex items-center justify-between rounded-lg bg-dark-800 p-3 border border-white/[0.04]">
              <div>
                <h4 className="text-sm font-medium text-slate-200">日志输出</h4>
                <p className="text-xs text-slate-500 mt-0.5">所有告警输出至标准输出/文件</p>
              </div>
              <Switch
                checked={logOutput}
                onChange={(v) => { setLogOutput(v); markChanged(); }}
                size="sm"
              />
            </div>

            {/* Telegram */}
            <div className="rounded-lg bg-dark-800 p-3 border border-white/[0.04]">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h4 className="text-sm font-medium text-slate-200">Telegram 通知</h4>
                  <p className="text-xs text-slate-500 mt-0.5">通过 Telegram Bot 发送告警消息</p>
                </div>
                <Switch
                  checked={telegramEnabled}
                  onChange={(v) => { setTelegramEnabled(v); markChanged(); }}
                  size="sm"
                />
              </div>
              <AnimatePresence>
                {telegramEnabled && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-white/[0.06]"
                  >
                    <Input
                      label="Bot Token"
                      type="password"
                      placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
                      value={telegramToken}
                      onChange={(e) => { setTelegramToken(e.target.value); markChanged(); }}
                    />
                    <Input
                      label="Chat ID"
                      placeholder="-1001234567890"
                      value={telegramChatId}
                      onChange={(e) => { setTelegramChatId(e.target.value); markChanged(); }}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Email */}
            <div className="rounded-lg bg-dark-800 p-3 border border-white/[0.04]">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h4 className="text-sm font-medium text-slate-200">邮件通知</h4>
                  <p className="text-xs text-slate-500 mt-0.5">通过 SMTP 发送告警邮件</p>
                </div>
                <Switch
                  checked={emailEnabled}
                  onChange={(v) => { setEmailEnabled(v); markChanged(); }}
                  size="sm"
                />
              </div>
              <AnimatePresence>
                {emailEnabled && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="space-y-4 pt-3 border-t border-white/[0.06]"
                  >
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                      <Input
                        label="SMTP 主机"
                        placeholder="smtp.gmail.com"
                        value={smtpHost}
                        onChange={(e) => { setSmtpHost(e.target.value); markChanged(); }}
                      />
                      <Input
                        label="SMTP 端口"
                        type="number"
                        value={smtpPort}
                        onChange={(e) => { setSmtpPort(e.target.value); markChanged(); }}
                      />
                      <Input
                        label="SMTP 用户名"
                        placeholder="user@example.com"
                        value={smtpUser}
                        onChange={(e) => { setSmtpUser(e.target.value); markChanged(); }}
                      />
                      <Input
                        label="SMTP 密码"
                        type="password"
                        placeholder="应用密码"
                        value={smtpPass}
                        onChange={(e) => { setSmtpPass(e.target.value); markChanged(); }}
                      />
                    </div>
                    <Input
                      label="收件人邮箱"
                      type="email"
                      placeholder="alerts@example.com"
                      value={emailTo}
                      onChange={(e) => { setEmailTo(e.target.value); markChanged(); }}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Web Notifications */}
            <div className="flex items-center justify-between rounded-lg bg-dark-800 p-3 border border-white/[0.04]">
              <div>
                <h4 className="text-sm font-medium text-slate-200">Web通知</h4>
                <p className="text-xs text-slate-500 mt-0.5">在仪表盘界面显示实时告警通知</p>
              </div>
              <Switch
                checked={webNotifications}
                onChange={(v) => { setWebNotifications(v); markChanged(); }}
                size="sm"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleSave} loading={saving} disabled={!hasChanges}>
          保存告警设置
        </Button>
      </div>

      <SaveToast show={saved} message="告警设置已保存" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 5: 系统信息
// ---------------------------------------------------------------------------

function SystemTab() {
  const { data: health } = useSystemHealth();
  const { data: exchanges } = useExchanges();
  const { data: metrics } = useSystemMetrics();

  const systemHealth = health ?? mockSystemHealth;
  const exchangeList = exchanges ?? mockExchanges;
  const systemMetrics = metrics ?? mockSystemMetrics;

  const [testingExchange, setTestingExchange] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, "success" | "failed">>({});

  const handleTestConnection = useCallback((exchange: string) => {
    setTestingExchange(exchange);
    setTimeout(() => {
      setTestResults((prev) => ({ ...prev, [exchange]: "success" }));
      setTestingExchange(null);
    }, 1500);
  }, []);

  return (
    <div className="space-y-4">
      {/* System Health */}
      <Card>
        <CardHeader
          action={
            <Badge
              variant={
                systemHealth.status === "healthy" ? "success" :
                systemHealth.status === "degraded" ? "warning" : "danger"
              }
              size="sm"
              dot
            >
              {systemHealth.status === "healthy" ? "正常" :
               systemHealth.status === "degraded" ? "降级" : "异常"}
            </Badge>
          }
        >
          系统健康状态
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">版本</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{systemHealth.version}</p>
            </div>
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">运行时间</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{formatDuration(systemHealth.uptime)}</p>
            </div>
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">内存使用</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{systemHealth.memoryUsageMb} MB</p>
            </div>
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">CPU 使用率</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{systemHealth.cpuUsagePercent}%</p>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3">
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">活跃策略</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{systemHealth.activeStrategies}</p>
            </div>
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">消息/秒</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{systemMetrics.messagesPerSecond}</p>
            </div>
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">订单/分</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{systemMetrics.ordersPerMinute}</p>
            </div>
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">24h 成交量</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{formatCurrency(systemMetrics.totalVolume24h, { compact: true })}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Service Status */}
      <Card>
        <CardHeader>服务状态</CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex items-center justify-between rounded-lg bg-dark-800 p-4 border border-white/[0.04]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-dark-700">
                  <svg className="h-5 w-5 text-slate-400" viewBox="0 0 20 20" fill="currentColor">
                    <path d="M3 12v3c0 1.657 3.134 3 7 3s7-1.343 7-3v-3c0 1.657-3.134 3-7 3s-7-1.343-7-3z" />
                    <path d="M3 7v3c0 1.657 3.134 3 7 3s7-1.343 7-3V7c0 1.657-3.134 3-7 3S3 8.657 3 7z" />
                    <path d="M17 5c0 1.657-3.134 3-7 3S3 6.657 3 5s3.134-3 7-3 7 1.343 7 3z" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-200">PostgreSQL</p>
                  <p className="text-xs text-slate-500">主数据库</p>
                </div>
              </div>
              <StatusDot status="connected" label="已连接" />
            </div>

            <div className="flex items-center justify-between rounded-lg bg-dark-800 p-4 border border-white/[0.04]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-dark-700">
                  <svg className="h-5 w-5 text-slate-400" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v2a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm14 1a1 1 0 11-2 0 1 1 0 012 0zM2 13a2 2 0 012-2h12a2 2 0 012 2v2a2 2 0 01-2 2H4a2 2 0 01-2-2v-2zm14 1a1 1 0 11-2 0 1 1 0 012 0z" clipRule="evenodd" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-200">Redis</p>
                  <p className="text-xs text-slate-500">缓存 & 消息订阅</p>
                </div>
              </div>
              <StatusDot status="connected" label="已连接" />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Exchange API Connections */}
      <Card>
        <CardHeader>交易所 API 连接</CardHeader>
        <CardContent>
          <div className="space-y-3">
            {exchangeList.map((exchange) => (
              <div
                key={exchange.exchange}
                className="flex items-center justify-between rounded-lg bg-dark-800 p-3 border border-white/[0.04]"
              >
                <div className="flex items-center gap-3">
                  <StatusDot
                    status={
                      exchange.status === "healthy" ? "connected" :
                      exchange.status === "degraded" ? "degraded" : "disconnected"
                    }
                  />
                  <div>
                    <p className="text-sm font-medium text-slate-200">{exchange.name}</p>
                    <div className="flex items-center gap-3 text-xs text-slate-500 mt-0.5">
                      <span>延迟: <span className="font-number text-slate-400">{exchange.latencyMs}ms</span></span>
                      <span>速率限制: <span className="font-number text-slate-400">{exchange.rateLimitRemaining}/{exchange.rateLimitTotal}</span></span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {testResults[exchange.exchange] && (
                    <Badge
                      variant={testResults[exchange.exchange] === "success" ? "success" : "danger"}
                      size="sm"
                    >
                      {testResults[exchange.exchange] === "success" ? "正常" : "失败"}
                    </Badge>
                  )}
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={testingExchange === exchange.exchange}
                    onClick={() => handleTestConnection(exchange.exchange)}
                  >
                    测试连接
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Version Info */}
      <Card>
        <CardHeader>版本信息</CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">应用版本</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{systemHealth.version}</p>
            </div>
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">运行时间</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{formatDuration(systemHealth.uptime)}</p>
            </div>
            <div className="rounded-lg bg-dark-800 p-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">连接数</p>
              <p className="text-sm font-semibold text-slate-200 font-number">{systemMetrics.activeConnections}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState("general");

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-xl font-semibold text-white">设置</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          配置交易参数、策略、风控规则和系统偏好
        </p>
      </div>

      {/* Tab Navigation */}
      <Tabs
        tabs={settingsTabs}
        activeTab={activeTab}
        onChange={setActiveTab}
      />

      {/* Tab Panels with animation */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2 }}
        >
          <TabPanel tabId="general" activeTab={activeTab}>
            <GeneralTab />
          </TabPanel>

          <TabPanel tabId="strategies" activeTab={activeTab}>
            <StrategiesTab />
          </TabPanel>

          <TabPanel tabId="risk" activeTab={activeTab}>
            <RiskRulesTab />
          </TabPanel>

          <TabPanel tabId="alerts" activeTab={activeTab}>
            <AlertsTab />
          </TabPanel>

          <TabPanel tabId="system" activeTab={activeTab}>
            <SystemTab />
          </TabPanel>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
