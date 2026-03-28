"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  TrendingUp,
  Zap,
  Activity,
  Wallet,
  Shield,
  BarChart3,
  Bell,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { StatusDot } from "@/components/ui/status-dot";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { useSettingsStore } from "@/store";

const navItems = [
  { label: "仪表盘", href: "/", icon: LayoutDashboard },
  { label: "行情", href: "/market", icon: TrendingUp },
  { label: "套利机会", href: "/opportunities", icon: Zap },
  { label: "执行记录", href: "/executions", icon: Activity },
  { label: "库存资产", href: "/inventory", icon: Wallet },
  { label: "风险控制", href: "/risk", icon: Shield },
  { label: "告警中心", href: "/alerts", icon: Bell },
  { label: "数据分析", href: "/analytics", icon: BarChart3 },
  { label: "系统设置", href: "/settings", icon: Settings },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const tradingMode = useSettingsStore((s) => s.tradingMode);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Close mobile sidebar on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Close mobile sidebar on resize to desktop
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 1024) {
        setMobileOpen(false);
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  const sidebarContent = (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div
        className={cn(
          "flex items-center border-b border-white/[0.06] px-4",
          collapsed ? "h-16 justify-center" : "h-16 gap-3"
        )}
      >
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary-500 to-accent-500">
          <Zap className="h-4 w-4 text-white" />
        </div>
        <AnimatePresence>
          {!collapsed && (
            <motion.span
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: "auto" }}
              exit={{ opacity: 0, width: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden whitespace-nowrap text-lg font-bold"
            >
              <span className="bg-gradient-to-r from-primary-400 to-accent-400 bg-clip-text text-transparent">
                ArbitrageX
              </span>
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {navItems.map((item) => {
          const active = isActive(item.href);
          const Icon = item.icon;

          const linkContent = (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative flex items-center rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                active
                  ? "text-white"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]",
                collapsed && "justify-center px-2"
              )}
            >
              {/* Active indicator - gradient left border */}
              {active && (
                <motion.div
                  layoutId="sidebar-active"
                  className="absolute inset-0 rounded-lg"
                  transition={{ type: "spring", stiffness: 350, damping: 30 }}
                >
                  <div className="absolute left-0 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-full bg-gradient-to-b from-primary-400 to-accent-400" />
                  <div className="absolute inset-0 rounded-lg bg-gradient-to-r from-primary-500/[0.08] to-transparent" />
                  <div className="absolute inset-0 rounded-lg shadow-[inset_0_0_12px_rgba(59,130,246,0.06)]" />
                </motion.div>
              )}

              <Icon
                className={cn(
                  "relative z-10 h-5 w-5 shrink-0 transition-colors",
                  active
                    ? "text-primary-400"
                    : "text-slate-500 group-hover:text-slate-300"
                )}
              />
              <AnimatePresence>
                {!collapsed && (
                  <motion.span
                    initial={{ opacity: 0, width: 0 }}
                    animate={{ opacity: 1, width: "auto" }}
                    exit={{ opacity: 0, width: 0 }}
                    transition={{ duration: 0.15 }}
                    className="relative z-10 ml-3 overflow-hidden whitespace-nowrap"
                  >
                    {item.label}
                  </motion.span>
                )}
              </AnimatePresence>
            </Link>
          );

          if (collapsed) {
            return (
              <Tooltip key={item.href} content={item.label} side="right">
                {linkContent}
              </Tooltip>
            );
          }

          return <React.Fragment key={item.href}>{linkContent}</React.Fragment>;
        })}
      </nav>

      {/* Bottom section */}
      <div className="border-t border-white/[0.06] px-3 py-4 space-y-3">
        {/* System status */}
        <div
          className={cn(
            "flex items-center",
            collapsed ? "justify-center" : "gap-2 px-3"
          )}
        >
          <StatusDot status="connected" />
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-xs text-slate-400"
              >
                系统在线
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {/* Trading mode badge */}
        <div
          className={cn(
            "flex items-center",
            collapsed ? "justify-center" : "px-3"
          )}
        >
          {collapsed ? (
            <Tooltip
              content={tradingMode === "paper" ? "模拟模式" : "实盘模式"}
              side="right"
            >
              <div>
                <Badge
                  variant={tradingMode === "live" ? "danger" : "warning"}
                  dot
                  size="sm"
                >
                  {tradingMode === "paper" ? "P" : "L"}
                </Badge>
              </div>
            </Tooltip>
          ) : (
            <Badge
              variant={tradingMode === "live" ? "danger" : "warning"}
              dot
              size="md"
            >
              {tradingMode === "paper" ? "模拟盘" : "实盘"}
            </Badge>
          )}
        </div>

        {/* Collapse toggle */}
        <button
          onClick={() => setCollapsed((prev) => !prev)}
          className={cn(
            "hidden lg:flex w-full items-center rounded-lg px-3 py-2 text-xs text-slate-500 transition-colors hover:text-slate-300 hover:bg-white/[0.04]",
            collapsed && "justify-center px-2"
          )}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <>
              <ChevronLeft className="h-4 w-4 mr-2" />
              收起
            </>
          )}
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile hamburger button */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed top-4 left-4 z-50 flex h-9 w-9 items-center justify-center rounded-lg bg-dark-800 border border-white/[0.08] text-slate-400 hover:text-white lg:hidden"
        aria-label="打开导航"
      >
        <svg
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 6h16M4 12h16M4 18h16"
          />
        </svg>
      </button>

      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Mobile sidebar */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.aside
            initial={{ x: -280 }}
            animate={{ x: 0 }}
            exit={{ x: -280 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="fixed inset-y-0 left-0 z-50 w-[260px] border-r border-white/[0.06] bg-dark-900/95 backdrop-blur-xl lg:hidden"
          >
            {sidebarContent}
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Desktop sidebar */}
      <motion.aside
        initial={false}
        animate={{ width: collapsed ? 72 : 260 }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className={cn(
          "hidden lg:flex fixed inset-y-0 left-0 z-30 flex-col",
          "border-r border-white/[0.06] bg-dark-900/80 backdrop-blur-xl"
        )}
      >
        {sidebarContent}
      </motion.aside>

      {/* Spacer to push content */}
      <motion.div
        initial={false}
        animate={{ width: collapsed ? 72 : 260 }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className="hidden lg:block shrink-0"
      />
    </>
  );
}
