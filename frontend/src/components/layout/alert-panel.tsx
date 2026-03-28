"use client";

import React, { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  AlertTriangle,
  AlertCircle,
  Info,
  ShieldAlert,
  Check,
  Eye,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatTimeAgo } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAlertStore } from "@/store";
import { useAlerts } from "@/hooks/useApi";
import type { Alert, AlertSeverity } from "@/types";

interface AlertPanelProps {
  open: boolean;
  onClose: () => void;
}

const severityConfig: Record<
  AlertSeverity,
  {
    icon: React.ElementType;
    color: string;
    bg: string;
    border: string;
    badge: "danger" | "warning" | "info" | "neutral";
  }
> = {
  critical: {
    icon: ShieldAlert,
    color: "text-danger-400",
    bg: "bg-danger-500/[0.06]",
    border: "border-l-danger-500",
    badge: "danger",
  },
  error: {
    icon: AlertCircle,
    color: "text-danger-400",
    bg: "bg-danger-500/[0.04]",
    border: "border-l-danger-400",
    badge: "danger",
  },
  warning: {
    icon: AlertTriangle,
    color: "text-warning-400",
    bg: "bg-warning-500/[0.04]",
    border: "border-l-warning-400",
    badge: "warning",
  },
  info: {
    icon: Info,
    color: "text-primary-400",
    bg: "bg-primary-500/[0.04]",
    border: "border-l-primary-400",
    badge: "info",
  },
};

export function AlertPanel({ open, onClose }: AlertPanelProps) {
  const storeAlerts = useAlertStore((s) => s.alerts);
  const markRead = useAlertStore((s) => s.markRead);
  const resolveAlert = useAlertStore((s) => s.resolveAlert);
  const { data: apiAlerts } = useAlerts();
  const apiAlertList: Alert[] = Array.isArray(apiAlerts) ? apiAlerts : (apiAlerts?.data ?? []);

  const alerts = storeAlerts.length > 0 ? storeAlerts : apiAlertList;

  // Close on escape
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className={cn(
              "fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col",
              "border-l border-white/[0.06] bg-dark-900/95 backdrop-blur-xl shadow-2xl"
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
              <div className="flex items-center gap-3">
                <h2 className="text-base font-semibold text-white">系统告警</h2>
                <Badge variant="neutral" size="sm">
                  {alerts.filter((a) => !a.read).length} 未读
                </Badge>
              </div>
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="h-5 w-5" />
              </Button>
            </div>

            {/* Alert list */}
            <div className="flex-1 overflow-y-auto">
              {alerts.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                  <Info className="h-10 w-10 mb-3 opacity-40" />
                  <p className="text-sm">暂无告警</p>
                </div>
              ) : (
                <div className="divide-y divide-white/[0.04]">
                  {alerts.map((alert) => (
                    <AlertItem
                      key={alert.id}
                      alert={alert}
                      onMarkRead={() => markRead(alert.id)}
                      onResolve={() => resolveAlert(alert.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function AlertItem({
  alert,
  onMarkRead,
  onResolve,
}: {
  alert: Alert;
  onMarkRead: () => void;
  onResolve: () => void;
}) {
  const config = severityConfig[alert.severity];
  const Icon = config.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "relative border-l-2 px-5 py-4 transition-colors",
        config.border,
        config.bg,
        !alert.read && "bg-white/[0.02]"
      )}
    >
      {/* Unread indicator */}
      {!alert.read && (
        <div className="absolute top-5 right-5 h-2 w-2 rounded-full bg-primary-400" />
      )}

      <div className="flex items-start gap-3">
        <div
          className={cn(
            "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
            config.color,
            "bg-white/[0.04]"
          )}
        >
          <Icon className="h-4 w-4" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium text-white truncate">
              {alert.title}
            </span>
            <Badge variant={config.badge} size="sm">
              {alert.severity}
            </Badge>
          </div>

          <p className="text-xs text-slate-400 leading-relaxed mb-2">
            {alert.message}
          </p>

          <div className="flex items-center justify-between">
            <span className="text-[10px] text-slate-600 font-number">
              {formatTimeAgo(alert.createdAt)}
            </span>

            <div className="flex items-center gap-1.5">
              {!alert.read && (
                <button
                  onClick={onMarkRead}
                  className="flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium text-slate-500 transition-colors hover:bg-white/[0.06] hover:text-slate-300"
                >
                  <Eye className="h-3 w-3" />
                  标记已读
                </button>
              )}
              {!alert.resolved && (
                <button
                  onClick={onResolve}
                  className="flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium text-success-500/70 transition-colors hover:bg-success-500/10 hover:text-success-400"
                >
                  <Check className="h-3 w-3" />
                  已处理
                </button>
              )}
              {alert.resolved && (
                <span className="flex items-center gap-1 text-[10px] text-success-500/50">
                  <Check className="h-3 w-3" />
                  已处理
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
