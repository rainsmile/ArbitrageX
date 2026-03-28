"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  change?: {
    value: number;
    label?: string;
  };
  icon?: React.ReactNode;
  prefix?: string;
  suffix?: string;
  variant?: "default" | "glass";
  className?: string;
}

export function StatCard({
  label,
  value,
  change,
  icon,
  prefix,
  suffix,
  variant = "default",
  className,
}: StatCardProps) {
  const isPositive = change && change.value >= 0;
  const isNegative = change && change.value < 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn(
        "rounded-xl p-4 transition-all duration-300",
        variant === "default" &&
          "bg-dark-900 border border-white/[0.06]",
        variant === "glass" &&
          "bg-dark-900/60 backdrop-blur-xl border border-white/[0.06]",
        "hover:border-white/[0.1]",
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            {label}
          </p>
          <p className="text-2xl font-semibold text-white font-number truncate">
            {prefix}
            {typeof value === "number" ? value.toLocaleString() : value}
            {suffix && (
              <span className="text-sm text-slate-400 ml-1">{suffix}</span>
            )}
          </p>
          {change && (
            <div className="flex items-center gap-1.5 mt-2">
              <span
                className={cn(
                  "inline-flex items-center gap-0.5 text-xs font-medium font-number",
                  isPositive && "text-success-400",
                  isNegative && "text-danger-400"
                )}
              >
                {isPositive ? (
                  <svg
                    className="h-3 w-3"
                    viewBox="0 0 12 12"
                    fill="none"
                  >
                    <path
                      d="M6 9.5V2.5M6 2.5L2.5 6M6 2.5L9.5 6"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  <svg
                    className="h-3 w-3"
                    viewBox="0 0 12 12"
                    fill="none"
                  >
                    <path
                      d="M6 2.5V9.5M6 9.5L2.5 6M6 9.5L9.5 6"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
                {isPositive ? "+" : ""}
                {change.value.toFixed(2)}%
              </span>
              {change.label && (
                <span className="text-xs text-slate-600">{change.label}</span>
              )}
            </div>
          )}
        </div>
        {icon && (
          <div className="shrink-0 ml-3 p-2 rounded-lg bg-dark-800 text-slate-400 [&>svg]:h-5 [&>svg]:w-5">
            {icon}
          </div>
        )}
      </div>
    </motion.div>
  );
}
