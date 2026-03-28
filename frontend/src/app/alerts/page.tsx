'use client';

import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { StatCard } from '@/components/ui/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import {
  formatTimeAgo,
  formatDate,
  cn,
} from '@/lib/utils';
import {
  useAlerts,
  useActiveAlerts,
  useAcknowledgeAlert,
  useResolveAlert,
} from '@/hooks/useApi';
import type { Alert, AlertSeverity, AlertCategory } from '@/types';

// ---------------------------------------------------------------------------
// Animation variants
// ---------------------------------------------------------------------------

const stagger = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' as const } },
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SEVERITY_CONFIG: Record<string, {
  label: string;
  variant: 'danger' | 'warning' | 'info' | 'neutral';
  color: string;
  bg: string;
  border: string;
  glowBorder: string;
  icon: React.ReactNode;
}> = {
  critical: {
    label: '严重',
    variant: 'danger',
    color: 'text-red-400',
    bg: 'bg-red-500/5',
    border: 'border-red-500/20',
    glowBorder: 'shadow-[0_0_12px_rgba(239,68,68,0.08)] border-red-500/30',
    icon: (
      <svg className="w-4 h-4 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="15" y1="9" x2="9" y2="15" />
        <line x1="9" y1="9" x2="15" y2="15" />
      </svg>
    ),
  },
  error: {
    label: '严重',
    variant: 'danger',
    color: 'text-red-400',
    bg: 'bg-red-500/5',
    border: 'border-red-500/20',
    glowBorder: 'shadow-[0_0_12px_rgba(239,68,68,0.08)] border-red-500/30',
    icon: (
      <svg className="w-4 h-4 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
    ),
  },
  warning: {
    label: '警告',
    variant: 'warning',
    color: 'text-yellow-400',
    bg: 'bg-yellow-500/5',
    border: 'border-yellow-500/15',
    glowBorder: 'shadow-[0_0_10px_rgba(234,179,8,0.06)] border-yellow-500/25',
    icon: (
      <svg className="w-4 h-4 text-yellow-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    ),
  },
  info: {
    label: '信息',
    variant: 'info',
    color: 'text-blue-400',
    bg: 'bg-blue-500/5',
    border: 'border-white/[0.06]',
    glowBorder: 'border-white/[0.06]',
    icon: (
      <svg className="w-4 h-4 text-blue-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
    ),
  },
};

const CATEGORY_LABEL: Record<string, string> = {
  opportunity: '机会',
  execution: '执行',
  risk: '风控',
  system: '系统',
  balance: '余额',
  connectivity: '连接',
};

const CATEGORY_VARIANT: Record<string, 'success' | 'danger' | 'warning' | 'info' | 'neutral'> = {
  opportunity: 'success',
  execution: 'info',
  risk: 'danger',
  system: 'neutral',
  balance: 'warning',
  connectivity: 'warning',
};

type StatusFilter = 'all' | 'unread' | 'acknowledged' | 'resolved';

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AlertsPage() {
  const { data: alertsResp } = useAlerts();
  const { data: activeAlerts } = useActiveAlerts();
  const acknowledgeMutation = useAcknowledgeAlert();
  const resolveMutation = useResolveAlert();

  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const allAlerts: Alert[] = alertsResp?.data ?? [];

  // ---- Stats ----
  const totalCount = allAlerts.length;
  const unreadCount = allAlerts.filter((a) => !a.read).length;
  const criticalCount = allAlerts.filter((a) => a.severity === 'critical' || a.severity === 'error').length;
  const todayCount = useMemo(() => {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    return allAlerts.filter((a) => new Date(a.createdAt) >= todayStart).length;
  }, [allAlerts]);

  // ---- Filtered alerts ----
  const filteredAlerts = useMemo(() => {
    let result = [...allAlerts];

    if (severityFilter !== 'all') {
      result = result.filter((a) => a.severity === severityFilter);
    }
    if (categoryFilter !== 'all') {
      result = result.filter((a) => a.category === categoryFilter);
    }
    if (statusFilter === 'unread') {
      result = result.filter((a) => !a.read);
    } else if (statusFilter === 'acknowledged') {
      result = result.filter((a) => a.read && !a.resolved);
    } else if (statusFilter === 'resolved') {
      result = result.filter((a) => a.resolved);
    }

    return result.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }, [allAlerts, severityFilter, categoryFilter, statusFilter]);

  // ---- Filter options ----
  const severityOptions = [
    { value: 'all', label: '全部级别' },
    { value: 'critical', label: '严重' },
    { value: 'error', label: '错误' },
    { value: 'warning', label: '警告' },
    { value: 'info', label: '信息' },
  ];

  const categoryOptions = [
    { value: 'all', label: '全部类型' },
    { value: 'execution', label: '执行' },
    { value: 'risk', label: '风控' },
    { value: 'connectivity', label: '连接' },
    { value: 'balance', label: '余额' },
    { value: 'opportunity', label: '机会' },
    { value: 'system', label: '系统' },
  ];

  const statusOptions = [
    { value: 'all', label: '全部状态' },
    { value: 'unread', label: '未读' },
    { value: 'acknowledged', label: '已确认' },
    { value: 'resolved', label: '已解决' },
  ];

  // ---- Actions ----
  const handleAcknowledge = (id: string) => {
    acknowledgeMutation.mutate(id);
  };

  const handleResolve = (id: string) => {
    resolveMutation.mutate(id);
  };

  const getAlertStatus = (alert: Alert): { label: string; variant: 'success' | 'danger' | 'warning' | 'info' | 'neutral' } => {
    if (alert.resolved) return { label: '已解决', variant: 'success' };
    if (alert.read) return { label: '已确认', variant: 'neutral' };
    return { label: '未读', variant: 'warning' };
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-xl font-semibold text-white">告警中心</h1>
        <p className="text-sm text-slate-500 mt-1">查看和管理系统告警、风险提示与运行通知</p>
      </div>

      {/* ================================================================ */}
      {/* Top Section: 4 Stat Cards                                        */}
      {/* ================================================================ */}
      <motion.div variants={stagger} initial="hidden" animate="show" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div variants={fadeUp}>
          <StatCard
            label="总告警数"
            value={totalCount}
            icon={
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 01-3.46 0" />
              </svg>
            }
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <StatCard
            label="未处理告警"
            value={unreadCount}
            icon={
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            }
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <StatCard
            label="严重告警"
            value={criticalCount}
            icon={
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            }
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <StatCard
            label="今日新增"
            value={todayCount}
            icon={
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            }
          />
        </motion.div>
      </motion.div>

      {/* ================================================================ */}
      {/* Filter Bar                                                        */}
      {/* ================================================================ */}
      <Card>
        <CardContent className="py-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs text-slate-500 font-medium">筛选:</span>
            <Select
              options={severityOptions}
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="w-28"
            />
            <Select
              options={categoryOptions}
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="w-28"
            />
            <Select
              options={statusOptions}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              className="w-28"
            />
            <span className="text-xs text-slate-600 ml-auto">
              {filteredAlerts.length} / {totalCount} 条告警
            </span>
          </div>
        </CardContent>
      </Card>

      {/* ================================================================ */}
      {/* Alert List                                                        */}
      {/* ================================================================ */}
      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {filteredAlerts.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="py-16 text-center text-sm text-slate-600"
            >
              没有匹配筛选条件的告警
            </motion.div>
          ) : (
            filteredAlerts.map((alert, idx) => {
              const sev = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.info;
              const status = getAlertStatus(alert);
              const isExpanded = expandedId === alert.id;
              const isUnread = !alert.read;
              const isResolved = alert.resolved;

              return (
                <motion.div
                  key={alert.id}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ delay: idx * 0.03 }}
                >
                  <div
                    className={cn(
                      'rounded-xl border transition-all cursor-pointer',
                      // Severity-based border treatment
                      isUnread ? sev.glowBorder : sev.border,
                      // Background
                      isResolved ? 'bg-dark-900/50 opacity-60' : sev.bg,
                      // Unread emphasis
                      isUnread && !isResolved && 'ring-1 ring-white/[0.04]',
                    )}
                    onClick={() => setExpandedId(isExpanded ? null : alert.id)}
                  >
                    {/* Main alert row */}
                    <div className="p-4">
                      <div className="flex items-start gap-3">
                        {/* Severity icon */}
                        <div className="shrink-0 mt-0.5">{sev.icon}</div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <span className={cn(
                              'text-sm font-medium',
                              isUnread ? 'text-white' : 'text-slate-300',
                              isResolved && 'text-slate-500',
                            )}>
                              {alert.title}
                            </span>
                            <Badge variant={sev.variant} size="sm">{sev.label}</Badge>
                            <Badge variant={CATEGORY_VARIANT[alert.category] || 'neutral'} size="sm">
                              {CATEGORY_LABEL[alert.category] || alert.category}
                            </Badge>
                            <Badge variant={status.variant} size="sm">{status.label}</Badge>
                          </div>

                          <p className={cn(
                            'text-xs leading-relaxed',
                            isResolved ? 'text-slate-600' : 'text-slate-400',
                            !isExpanded && 'line-clamp-2',
                          )}>
                            {alert.message}
                          </p>

                          <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-600">
                            <span>来源: <span className="text-slate-400">{CATEGORY_LABEL[alert.category] || alert.category}</span></span>
                            <span>{formatTimeAgo(alert.createdAt)}</span>
                          </div>
                        </div>

                        {/* Action buttons */}
                        <div className="shrink-0 flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                          {!alert.read && !alert.resolved && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleAcknowledge(alert.id)}
                              className="text-xs"
                            >
                              确认
                            </Button>
                          )}
                          {!alert.resolved && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleResolve(alert.id)}
                              className="text-xs"
                            >
                              解决
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Expanded detail section */}
                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          className="overflow-hidden"
                        >
                          <div className="px-4 pb-4 pt-0 border-t border-white/[0.04]">
                            <div className="pt-3 space-y-3">
                              {/* Full message */}
                              <div>
                                <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">完整消息</p>
                                <p className="text-xs text-slate-300 leading-relaxed">{alert.message}</p>
                              </div>

                              {/* Details JSON */}
                              {alert.details && Object.keys(alert.details).length > 0 && (
                                <div>
                                  <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">详细信息</p>
                                  <div className="rounded-lg bg-dark-800/60 border border-white/[0.04] p-3">
                                    <div className="space-y-1.5">
                                      {Object.entries(alert.details).map(([key, value]) => (
                                        <div key={key} className="flex items-baseline gap-2">
                                          <span className="text-[10px] text-slate-600 w-28 shrink-0">{key}</span>
                                          <span className="text-xs text-slate-300 font-number break-all">{String(value)}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                </div>
                              )}

                              {/* Resolution history */}
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">时间信息</p>
                                  <div className="space-y-1 text-xs">
                                    <div className="flex justify-between">
                                      <span className="text-slate-600">创建时间</span>
                                      <span className="text-slate-400 font-number">{formatDate(alert.createdAt, { format: 'datetime' })}</span>
                                    </div>
                                    <div className="flex justify-between">
                                      <span className="text-slate-600">更新时间</span>
                                      <span className="text-slate-400 font-number">{formatDate(alert.updatedAt, { format: 'datetime' })}</span>
                                    </div>
                                    {alert.resolvedAt && (
                                      <div className="flex justify-between">
                                        <span className="text-slate-600">解决时间</span>
                                        <span className="text-slate-400 font-number">{formatDate(alert.resolvedAt, { format: 'datetime' })}</span>
                                      </div>
                                    )}
                                  </div>
                                </div>
                                <div>
                                  <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">解决记录</p>
                                  <div className="space-y-1 text-xs">
                                    <div className="flex justify-between">
                                      <span className="text-slate-600">状态</span>
                                      <Badge variant={status.variant} size="sm">{status.label}</Badge>
                                    </div>
                                    {alert.resolvedBy && (
                                      <div className="flex justify-between">
                                        <span className="text-slate-600">解决者</span>
                                        <span className="text-slate-400">{alert.resolvedBy}</span>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </motion.div>
              );
            })
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
