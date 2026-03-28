"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface ProgressProps {
  value: number;
  max?: number;
  variant?: "default" | "success" | "danger" | "warning" | "accent";
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  className?: string;
}

const gradients: Record<string, string> = {
  default: "from-primary-600 to-primary-400",
  success: "from-success-600 to-success-400",
  danger: "from-danger-600 to-danger-400",
  warning: "from-warning-600 to-warning-400",
  accent: "from-accent-600 to-accent-400",
};

const glowColors: Record<string, string> = {
  default: "shadow-[0_0_8px_rgba(59,130,246,0.4)]",
  success: "shadow-[0_0_8px_rgba(34,197,94,0.4)]",
  danger: "shadow-[0_0_8px_rgba(239,68,68,0.4)]",
  warning: "shadow-[0_0_8px_rgba(245,158,11,0.4)]",
  accent: "shadow-[0_0_8px_rgba(6,182,212,0.4)]",
};

const sizeStyles: Record<string, string> = {
  sm: "h-1",
  md: "h-2",
  lg: "h-3",
};

export function Progress({
  value,
  max = 100,
  variant = "default",
  size = "md",
  showLabel = false,
  className,
}: ProgressProps) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));

  return (
    <div className={cn("w-full", className)}>
      {showLabel && (
        <div className="flex justify-between mb-1.5 text-xs text-slate-400">
          <span>Progress</span>
          <span className="font-number">{percentage.toFixed(0)}%</span>
        </div>
      )}
      <div
        className={cn(
          "w-full rounded-full bg-dark-800 overflow-hidden",
          sizeStyles[size]
        )}
      >
        <motion.div
          className={cn(
            "h-full rounded-full bg-gradient-to-r",
            gradients[variant],
            glowColors[variant]
          )}
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}
