'use client';

import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { StatCard } from '@/components/ui/stat-card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
import {
  formatCurrency,
  formatNumber,
  formatTimeAgo,
  formatDate,
  cn,
} from '@/lib/utils';
import {
  useRiskRules,
  useRiskEvents,
  useRiskExposure,
} from '@/hooks/useApi';
import type { RiskRule, RiskEvent, ExchangeId } from '@/types';

// ---------------------------------------------------------------------------
// Animation variants
// ---------------------------------------------------------------------------

const stagger = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' as const } },
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EXCHANGE_COLORS: Record<string, string> = {
  binance: '#f59e0b',
  okx: '#3b82f6',
  bybit: '#a78bfa',
};

const EXCHANGE_LABELS: Record<string, string> = {
  binance: 'Binance',
  okx: 'OKX',
  bybit: 'Bybit',
};

const SEVERITY_CONFIG: Record<string, { color: string; bg: string; border: string; label: string; variant: 'danger' | 'warning' | 'info' | 'success' }> = {
  critical: { color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20', label: '严重', variant: 'danger' },
  high: { color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20', label: '严重', variant: 'danger' },
  medium: { color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/20', label: '警告', variant: 'warning' },
  low: { color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20', label: '信息', variant: 'info' },
};

/** Rule categories with Chinese names and the rule types in each */
const RULE_CATEGORY_MAP: { key: string; label: string; color: string; types: string[] }[] = [
  { key: 'trade_limit', label: '交易限制', color: '#3b82f6', types: ['max_position_size', 'rate_limit', 'max_exposure'] },
  { key: 'profit_protect', label: '利润保护', color: '#10b981', types: ['min_balance'] },
  { key: 'risk_control', label: '风险控制', color: '#f87171', types: ['max_slippage', 'max_daily_loss', 'circuit_breaker'] },
  { key: 'data_quality', label: '数据质量', color: '#f59e0b', types: ['max_drawdown'] },
];

const RULE_NAME_CN: Record<string, string> = {
  'Max Position Size': '最大仓位限额',
  'Max Daily Loss': '每日最大亏损',
  'Max Drawdown': '最大回撤',
  'Max Total Exposure': '最大总敞口',
  'Min Exchange Balance': '最低余额',
  'Max Slippage': '最大滑点',
  'Order Rate Limit': '下单频率限制',
  'Circuit Breaker': '熔断机制',
};

const ACTION_VARIANT: Record<string, 'success' | 'danger' | 'warning' | 'info' | 'neutral'> = {
  warn: 'warning',
  block: 'danger',
  reduce: 'info',
  halt: 'danger',
  monitor: 'neutral',
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function RiskPage() {
  const { data: apiRules } = useRiskRules();
  const { data: apiEvents } = useRiskEvents();
  const { data: exposure } = useRiskExposure();

  const [localRules, setLocalRules] = useState<RiskRule[] | null>(null);

  // Merge API data with local overrides
  const rules: RiskRule[] = localRules ?? apiRules ?? [];
  const events: RiskEvent[] = apiEvents ?? [];

  // ---- Computed: overall risk status ----
  const overallStatus = useMemo(() => {
    const hasCritical = events.some((e) => e.severity === 'high' || e.severity === 'critical');
    const hasWarning = events.some((e) => e.severity === 'medium');
    if (hasCritical) return { label: '危险', color: 'text-red-400', dot: 'bg-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20' };
    if (hasWarning) return { label: '警告', color: 'text-yellow-400', dot: 'bg-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/20' };
    return { label: '正常', color: 'text-emerald-400', dot: 'bg-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' };
  }, [events]);

  const enabledCount = rules.filter((r) => r.enabled).length;
  const blockedToday = events.filter((e) => e.triggered).length;
  const totalExposure = exposure?.totalExposureUsd ?? 0;

  // ---- Grouped rules by category ----
  const groupedRules = useMemo(() => {
    const result: { key: string; label: string; color: string; rules: RiskRule[] }[] = [];
    for (const cat of RULE_CATEGORY_MAP) {
      const catRules = rules.filter((r) => cat.types.includes(r.type));
      if (catRules.length > 0) {
        result.push({ key: cat.key, label: cat.label, color: cat.color, rules: catRules });
      }
    }
    // Add uncategorized rules
    const categorized = new Set(RULE_CATEGORY_MAP.flatMap((c) => c.types));
    const uncategorized = rules.filter((r) => !categorized.has(r.type));
    if (uncategorized.length > 0) {
      result.push({ key: 'other', label: '其他', color: '#64748b', rules: uncategorized });
    }
    return result;
  }, [rules]);

  // ---- Sorted events ----
  const sortedEvents = useMemo(
    () => [...events].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()),
    [events],
  );

  // ---- Exchange exposures ----
  const exchangeExposures = useMemo(() => {
    if (!exposure) return [];
    return Object.entries(exposure.byExchange)
      .filter(([, val]) => val > 0)
      .map(([exchange, value]) => ({
        exchange: exchange as ExchangeId,
        value,
        percent: exposure.totalExposureUsd > 0 ? (value / exposure.totalExposureUsd) * 100 : 0,
        limitPercent: exposure.maxExposureUsd > 0 ? (value / exposure.maxExposureUsd) * 100 : 0,
      }))
      .sort((a, b) => b.value - a.value);
  }, [exposure]);

  // ---- Symbol exposures ----
  const symbolExposures = useMemo(() => {
    if (!exposure) return [];
    return Object.entries(exposure.bySymbol)
      .map(([symbol, value]) => ({
        symbol,
        value,
        percent: exposure.totalExposureUsd > 0 ? (value / exposure.totalExposureUsd) * 100 : 0,
      }))
      .sort((a, b) => b.value - a.value);
  }, [exposure]);

  // ---- HHI concentration risk ----
  const hhi = useMemo(() => {
    if (!exposure || exposure.totalExposureUsd === 0) return 0;
    const shares = Object.values(exposure.byExchange).filter((v) => v > 0).map((v) => v / exposure.totalExposureUsd);
    return shares.reduce((sum, s) => sum + s * s, 0);
  }, [exposure]);

  const hhiPercent = Math.min(hhi * 100, 100);
  const hhiLabel = hhi < 0.25 ? '低' : hhi < 0.5 ? '中' : '高';
  const hhiVariant = hhi < 0.25 ? 'success' : hhi < 0.5 ? 'warning' : 'danger';

  // ---- Toggle rule ----
  const toggleRule = (ruleId: string) => {
    const base = localRules ?? apiRules ?? [];
    setLocalRules(base.map((r) => (r.id === ruleId ? { ...r, enabled: !r.enabled } : r)));
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-xl font-semibold text-white">风险管理</h1>
        <p className="text-sm text-slate-500 mt-1">监控风险敞口、管理风控规则、审查风险事件</p>
      </div>

      {/* ================================================================== */}
      {/* Top Section: 4 Overview Cards                                      */}
      {/* ================================================================== */}
      <motion.div variants={stagger} initial="hidden" animate="show" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 风控状态 */}
        <motion.div variants={fadeUp}>
          <div className={cn('rounded-xl p-4 border transition-all', overallStatus.bg, overallStatus.border)}>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">风控状态</p>
            <p className={cn('text-2xl font-bold', overallStatus.color)}>{overallStatus.label}</p>
            <div className="flex items-center gap-1.5 mt-2">
              <span className={cn('h-2 w-2 rounded-full animate-pulse', overallStatus.dot)} />
              <span className="text-xs text-slate-500">实时监控中</span>
            </div>
          </div>
        </motion.div>

        {/* 活跃风控规则 */}
        <motion.div variants={fadeUp}>
          <StatCard
            label="活跃风控规则"
            value={enabledCount}
            suffix={`/ ${rules.length}`}
            icon={
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            }
          />
        </motion.div>

        {/* 今日拦截次数 */}
        <motion.div variants={fadeUp}>
          <StatCard
            label="今日拦截次数"
            value={blockedToday}
            icon={
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            }
          />
        </motion.div>

        {/* 当前风险敞口 */}
        <motion.div variants={fadeUp}>
          <StatCard
            label="当前风险敞口"
            value={formatCurrency(totalExposure, { compact: true })}
            suffix="USDT"
            icon={
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
              </svg>
            }
          />
        </motion.div>
      </motion.div>

      {/* ================================================================== */}
      {/* Main 2-Column Layout                                               */}
      {/* ================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* ---- Left Column (60%): Risk Rules ---- */}
        <div className="lg:col-span-3 space-y-6">
          <Card>
            <CardHeader>风控规则面板</CardHeader>
            <CardContent>
              <div className="space-y-6">
                {groupedRules.map((group) => (
                  <div key={group.key}>
                    {/* Category heading */}
                    <div className="flex items-center gap-2 mb-3">
                      <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: group.color }} />
                      <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{group.label}</h3>
                      <span className="text-[10px] text-slate-600">({group.rules.length})</span>
                    </div>

                    <div className="space-y-2">
                      {group.rules.map((rule) => {
                        const usagePercent = rule.threshold > 0 ? (rule.currentValue / rule.threshold) * 100 : 0;
                        const isTriggered = rule.lastTriggered !== null;
                        const cnName = RULE_NAME_CN[rule.name] || rule.name;

                        return (
                          <motion.div
                            key={rule.id}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className={cn(
                              'rounded-lg border p-4 transition-all',
                              rule.enabled
                                ? 'border-white/[0.06] bg-dark-900'
                                : 'border-white/[0.03] bg-dark-900/50 opacity-50',
                            )}
                          >
                            <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                              {/* Name, description, hit count */}
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="text-sm font-medium text-white">{cnName}</span>
                                  <Badge variant={ACTION_VARIANT[rule.action] || 'neutral'} size="sm">
                                    {rule.action.toUpperCase()}
                                  </Badge>
                                </div>
                                <p className="text-xs text-slate-500 leading-relaxed mb-1">{rule.description}</p>
                                <div className="flex items-center gap-3 text-[10px] text-slate-600">
                                  <span>命中: <span className="text-slate-400 font-number">{isTriggered ? '1+' : '0'}</span></span>
                                  {isTriggered && rule.lastTriggered && (
                                    <span>最后触发: <span className="text-slate-400">{formatTimeAgo(rule.lastTriggered)}</span></span>
                                  )}
                                </div>
                              </div>

                              {/* Current value / threshold progress */}
                              <div className="w-44 shrink-0">
                                <div className="flex justify-between text-[10px] mb-1">
                                  <span className="text-slate-500">阈值: {formatNumber(rule.threshold)} {rule.unit}</span>
                                  <span className={cn('font-number', usagePercent > 75 ? 'text-warning-400' : 'text-slate-400')}>
                                    {usagePercent.toFixed(1)}%
                                  </span>
                                </div>
                                <Progress
                                  value={Math.min(usagePercent, 100)}
                                  variant={usagePercent > 90 ? 'danger' : usagePercent > 75 ? 'warning' : 'success'}
                                  size="sm"
                                />
                                <div className="text-[10px] text-slate-600 mt-0.5 font-number">
                                  当前: {formatNumber(rule.currentValue)} {rule.unit}
                                </div>
                              </div>

                              {/* Toggle switch */}
                              <div className="shrink-0 flex items-center gap-2">
                                <span className="text-[10px] text-slate-600">{rule.enabled ? '已启用' : '已禁用'}</span>
                                <Switch checked={rule.enabled} onChange={() => toggleRule(rule.id)} size="sm" />
                              </div>
                            </div>
                          </motion.div>
                        );
                      })}
                    </div>
                  </div>
                ))}

                {rules.length === 0 && (
                  <div className="py-12 text-center text-sm text-slate-600">暂无风控规则</div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ---- Right Column (40%): Risk Events Timeline ---- */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>风险事件时间线</CardHeader>
            <CardContent>
              {sortedEvents.length === 0 ? (
                <div className="py-12 text-center text-sm text-slate-600">暂无风险事件</div>
              ) : (
                <div className="relative">
                  {/* Timeline vertical line */}
                  <div className="absolute left-[11px] top-2 bottom-2 w-px bg-white/[0.06]" />

                  <div className="space-y-1">
                    {sortedEvents.map((event, idx) => {
                      const sev = SEVERITY_CONFIG[event.severity] || SEVERITY_CONFIG.low;

                      return (
                        <motion.div
                          key={event.id}
                          initial={{ opacity: 0, x: -6 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: idx * 0.04 }}
                          className="relative pl-8 py-2"
                        >
                          {/* Timeline dot */}
                          <div className={cn(
                            'absolute left-[5px] top-3.5 h-3 w-3 rounded-full border-2 border-dark-950',
                            sev.color === 'text-red-400' ? 'bg-red-400' : sev.color === 'text-yellow-400' ? 'bg-yellow-400' : 'bg-blue-400',
                          )} />

                          <div className={cn(
                            'rounded-lg border p-3 transition-colors',
                            sev.border, 'bg-dark-900 hover:border-white/[0.12]',
                          )}>
                            <div className="flex items-start justify-between gap-2 mb-1.5">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <Badge variant={sev.variant} size="sm" dot>{sev.label}</Badge>
                                <Badge variant="neutral" size="sm">{event.ruleName}</Badge>
                                {event.triggered && <Badge variant="danger" size="sm">已触发</Badge>}
                              </div>
                              <span className="text-[10px] text-slate-600 font-number shrink-0 whitespace-nowrap">
                                {formatTimeAgo(event.timestamp)}
                              </span>
                            </div>

                            <p className="text-xs text-slate-300 leading-relaxed mb-1.5">{event.message}</p>

                            {/* Compact details */}
                            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px]">
                              {event.details.threshold !== undefined && (
                                <span className="text-slate-600">阈值: <span className="text-slate-400 font-number">{String(event.details.threshold)}</span></span>
                              )}
                              {event.details.current !== undefined && (
                                <span className="text-slate-600">当前: <span className="text-slate-400 font-number">{formatCurrency(event.details.current as number, { compact: true })}</span></span>
                              )}
                              {event.details.loss !== undefined && (
                                <span className="text-slate-600">亏损: <span className="text-red-400 font-number">-${String(event.details.loss)}</span></span>
                              )}
                              {typeof event.details.execution === 'string' && (
                                <span className="text-slate-600">执行: <span className="text-primary-400 font-number">{event.details.execution}</span></span>
                              )}
                            </div>
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ================================================================== */}
      {/* Bottom Section: Exposure Details                                    */}
      {/* ================================================================== */}
      <Card>
        <CardHeader>风险敞口详情</CardHeader>
        <CardContent>
          {/* Overall exposure bar */}
          {exposure && (
            <div className="mb-6 p-4 rounded-lg bg-dark-800/50 border border-white/[0.04]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-slate-300">总体敞口</span>
                <span className="text-sm font-semibold font-number text-white">
                  {formatCurrency(exposure.totalExposureUsd)} / {formatCurrency(exposure.maxExposureUsd)}
                </span>
              </div>
              <Progress
                value={exposure.utilizationPercent}
                variant={exposure.utilizationPercent > 75 ? 'danger' : exposure.utilizationPercent > 50 ? 'warning' : 'success'}
                size="lg"
              />
              <div className="flex justify-between mt-1.5">
                <span className="text-[10px] text-slate-600">{exposure.utilizationPercent}% 已使用</span>
                <span className="text-[10px] text-slate-600">{exposure.openPositions} 个持仓, {exposure.pendingOrders} 个挂单</span>
              </div>
            </div>
          )}

          {/* Per-exchange exposure bar chart */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            {exchangeExposures.map((ex) => (
              <motion.div
                key={ex.exchange}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-lg border border-white/[0.06] bg-dark-900 p-4"
              >
                <div className="flex items-center gap-2 mb-3">
                  <span className="h-3 w-3 rounded-full" style={{ backgroundColor: EXCHANGE_COLORS[ex.exchange] }} />
                  <span className="text-sm font-medium text-slate-200">{EXCHANGE_LABELS[ex.exchange] || ex.exchange}</span>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between items-baseline">
                    <span className="text-lg font-semibold font-number text-white">{formatCurrency(ex.value, { compact: true })}</span>
                    <span className="text-xs text-slate-500 font-number">{ex.percent.toFixed(1)}%</span>
                  </div>
                  <Progress value={ex.limitPercent} variant={ex.limitPercent > 30 ? 'warning' : 'success'} size="sm" />
                  <span className="text-[10px] text-slate-600 font-number">{ex.limitPercent.toFixed(1)}% 最大敞口占比</span>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Per-asset exposure table */}
          <div className="p-4 rounded-lg bg-dark-800/50 border border-white/[0.04] mb-6">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">按交易对敞口</p>
            <div className="space-y-3">
              {symbolExposures.map((sym) => (
                <div key={sym.symbol} className="flex items-center gap-3">
                  <span className="text-xs text-slate-300 w-24 font-medium">{sym.symbol}</span>
                  <div className="flex-1">
                    <Progress value={sym.percent} variant="default" size="sm" />
                  </div>
                  <span className="text-xs text-slate-400 font-number w-24 text-right">{formatCurrency(sym.value, { compact: true })}</span>
                  <span className="text-[10px] text-slate-600 font-number w-12 text-right">{sym.percent.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>

          {/* Concentration risk HHI */}
          <div className="p-4 rounded-lg bg-dark-800/50 border border-white/[0.04]">
            <div className="flex items-center justify-between mb-2">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">集中度风险 (HHI)</p>
                <p className="text-[10px] text-slate-600 mt-0.5">赫芬达尔-赫希曼指数衡量交易所集中度</p>
              </div>
              <div className="text-right">
                <span className={cn(
                  'text-sm font-bold font-number',
                  hhiVariant === 'success' ? 'text-emerald-400' : hhiVariant === 'warning' ? 'text-yellow-400' : 'text-red-400',
                )}>
                  {(hhi * 10000).toFixed(0)}
                </span>
                <Badge variant={hhiVariant as 'success' | 'warning' | 'danger'} size="sm" className="ml-2">{hhiLabel}</Badge>
              </div>
            </div>
            <Progress value={hhiPercent} variant={hhiVariant as 'success' | 'warning' | 'danger'} size="md" />
            <div className="flex justify-between mt-1.5 text-[10px] text-slate-600">
              <span>0 (完全分散)</span>
              <span>10000 (完全集中)</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
