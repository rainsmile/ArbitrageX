"use client";

import React from "react";
import { cn } from "@/lib/utils";

type BadgeVariant = "success" | "danger" | "warning" | "info" | "neutral";

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  size?: "sm" | "md";
  dot?: boolean;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  success:
    "bg-success-500/15 text-success-400 border-success-500/20",
  danger:
    "bg-danger-500/15 text-danger-400 border-danger-500/20",
  warning:
    "bg-warning-500/15 text-warning-400 border-warning-500/20",
  info: "bg-primary-500/15 text-primary-400 border-primary-500/20",
  neutral:
    "bg-slate-500/15 text-slate-400 border-slate-500/20",
};

const dotColors: Record<BadgeVariant, string> = {
  success: "bg-success-400",
  danger: "bg-danger-400",
  warning: "bg-warning-400",
  info: "bg-primary-400",
  neutral: "bg-slate-400",
};

export function Badge({
  children,
  variant = "neutral",
  size = "sm",
  dot = false,
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-medium",
        size === "sm" && "px-2 py-0.5 text-[11px]",
        size === "md" && "px-2.5 py-1 text-xs",
        variantStyles[variant],
        className
      )}
    >
      {dot && (
        <span
          className={cn("h-1.5 w-1.5 rounded-full", dotColors[variant])}
        />
      )}
      {children}
    </span>
  );
}
