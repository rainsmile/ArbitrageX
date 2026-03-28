"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  color?: "primary" | "accent" | "white";
  className?: string;
}

const sizeStyles: Record<string, string> = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-10 w-10",
};

const colorStyles: Record<string, string> = {
  primary: "text-primary-500",
  accent: "text-accent-400",
  white: "text-white",
};

export function Spinner({
  size = "md",
  color = "primary",
  className,
}: SpinnerProps) {
  return (
    <div className={cn("relative", sizeStyles[size], className)}>
      <svg
        className={cn("animate-spin", sizeStyles[size], colorStyles[color])}
        viewBox="0 0 24 24"
        fill="none"
      >
        <circle
          className="opacity-20"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="3"
        />
        <path
          className="opacity-80"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
      <div
        className={cn(
          "absolute inset-0 rounded-full blur-md opacity-30",
          color === "primary" && "bg-primary-500",
          color === "accent" && "bg-accent-400",
          color === "white" && "bg-white"
        )}
      />
    </div>
  );
}
