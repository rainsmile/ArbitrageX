"use client";

import React from "react";
import { cn } from "@/lib/utils";

type StatusType = "connected" | "disconnected" | "degraded";

interface StatusDotProps {
  status: StatusType;
  label?: string;
  size?: "sm" | "md";
  className?: string;
}

const dotColors: Record<StatusType, string> = {
  connected: "bg-success-400",
  disconnected: "bg-danger-400",
  degraded: "bg-warning-400",
};

const pulseColors: Record<StatusType, string> = {
  connected: "bg-success-400",
  disconnected: "bg-danger-400",
  degraded: "bg-warning-400",
};

const labelColors: Record<StatusType, string> = {
  connected: "text-success-400",
  disconnected: "text-danger-400",
  degraded: "text-warning-400",
};

export function StatusDot({
  status,
  label,
  size = "sm",
  className,
}: StatusDotProps) {
  const dotSize = size === "sm" ? "h-2 w-2" : "h-2.5 w-2.5";
  const pulseSize = size === "sm" ? "h-2 w-2" : "h-2.5 w-2.5";

  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className="relative flex">
        <span
          className={cn(
            "absolute inline-flex rounded-full opacity-40",
            pulseSize,
            pulseColors[status],
            status !== "disconnected" && "animate-ping"
          )}
          style={{ animationDuration: "2s" }}
        />
        <span
          className={cn("relative inline-flex rounded-full", dotSize, dotColors[status])}
        />
      </span>
      {label && (
        <span className={cn("text-xs font-medium capitalize", labelColors[status])}>
          {label}
        </span>
      )}
    </span>
  );
}
