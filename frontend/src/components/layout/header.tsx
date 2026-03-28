"use client";

import React, { useState, useCallback } from "react";
import { usePathname } from "next/navigation";
import { Bell, CircleDot } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { StatusDot } from "@/components/ui/status-dot";
import { Tooltip } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { AlertPanel } from "./alert-panel";
import { useSettingsStore, useAlertStore } from "@/store";
import { useSystemMetrics, useExchanges } from "@/hooks/useApi";

const routeTitles: Record<string, string> = {
  "/": "仪表盘",
  "/market": "行情",
  "/opportunities": "套利机会",
  "/executions": "执行记录",
  "/inventory": "库存资产",
  "/risk": "风险控制",
  "/analytics": "数据分析",
  "/settings": "系统设置",
};

export function Header() {
  const pathname = usePathname();
  const tradingMode = useSettingsStore((s) => s.tradingMode);
  const setTradingMode = useSettingsStore((s) => s.setTradingMode);
  const unreadCount = useAlertStore((s) => s.unreadCount);
  const [alertPanelOpen, setAlertPanelOpen] = useState(false);

  const { data: systemMetrics } = useSystemMetrics();
  const { data: exchangeList } = useExchanges();

  // Derive page title from pathname
  const pageTitle =
    routeTitles[pathname] ??
    routeTitles[
      Object.keys(routeTitles).find((key) =>
        key !== "/" ? pathname.startsWith(key) : false
      ) ?? "/"
    ] ??
    "仪表盘";

  const displayUnread = unreadCount;

  const toggleTradingMode = useCallback(() => {
    setTradingMode(tradingMode === "paper" ? "live" : "paper");
  }, [tradingMode, setTradingMode]);

  return (
    <>
      <header
        className={cn(
          "sticky top-0 z-20 flex h-16 items-center justify-between gap-4 px-4 lg:px-6",
          "border-b border-white/[0.06] bg-dark-950/70 backdrop-blur-xl"
        )}
      >
        {/* Left: Page title (offset on mobile for hamburger) */}
        <div className="flex items-center gap-3 min-w-0 pl-12 lg:pl-0">
          <h1 className="text-lg font-semibold text-white truncate">
            {pageTitle}
          </h1>
        </div>

        {/* Center: Quick stats */}
        <div className="hidden md:flex items-center gap-6">
          <QuickStat
            label="今日盈亏"
            value={formatCurrency(systemMetrics?.totalPnl24h ?? 0)}
            positive={(systemMetrics?.totalPnl24h ?? 0) >= 0}
          />
          <div className="h-8 w-px bg-white/[0.06]" />
          <QuickStat
            label="活跃机会"
            value={String(systemMetrics?.opportunitiesDetected ?? 0)}
          />
          <div className="h-8 w-px bg-white/[0.06]" />
          <QuickStat
            label="成功率"
            value={formatPercent(systemMetrics?.executionSuccessRate ?? 0, {
              showSign: false,
            })}
          />
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-3">
          {/* Exchange connection dots */}
          <div className="hidden lg:flex items-center gap-2 mr-2">
            {(exchangeList ?? []).map((ex) => (
              <Tooltip
                key={ex.exchange}
                content={`${ex.name}: ${ex.latencyMs}ms`}
                side="bottom"
              >
                <div>
                  <StatusDot
                    status={
                      ex.status === "healthy"
                        ? "connected"
                        : ex.status === "degraded"
                          ? "degraded"
                          : "disconnected"
                    }
                    size="sm"
                  />
                </div>
              </Tooltip>
            ))}
          </div>

          {/* Trading mode toggle */}
          <button
            onClick={toggleTradingMode}
            className={cn(
              "flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold uppercase tracking-wider transition-all duration-200 border",
              tradingMode === "paper"
                ? "border-warning-500/30 bg-warning-500/10 text-warning-400 hover:bg-warning-500/20"
                : "border-danger-500/30 bg-danger-500/10 text-danger-400 hover:bg-danger-500/20"
            )}
          >
            <CircleDot className="h-3 w-3" />
            {tradingMode === "paper" ? "模拟" : "实盘"}
          </button>

          {/* Alert bell */}
          <div className="relative">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setAlertPanelOpen((prev) => !prev)}
              className="relative"
            >
              <Bell className="h-5 w-5" />
              {displayUnread > 0 && (
                <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger-500 px-1 text-[10px] font-bold text-white">
                  {displayUnread > 99 ? "99+" : displayUnread}
                </span>
              )}
            </Button>
          </div>
        </div>
      </header>

      {/* Alert slide-out panel */}
      <AlertPanel
        open={alertPanelOpen}
        onClose={() => setAlertPanelOpen(false)}
      />
    </>
  );
}

function QuickStat({
  label,
  value,
  positive,
}: {
  label: string;
  value: string;
  positive?: boolean;
}) {
  return (
    <div className="flex flex-col items-center">
      <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <span
        className={cn(
          "font-number text-sm font-semibold",
          positive === true && "text-success-400",
          positive === false && "text-danger-400",
          positive === undefined && "text-slate-200"
        )}
      >
        {value}
      </span>
    </div>
  );
}
