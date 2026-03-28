import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind CSS classes with clsx and tailwind-merge
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a number as currency (USD by default)
 */
export function formatCurrency(
  value: number,
  options?: {
    currency?: string;
    minimumFractionDigits?: number;
    maximumFractionDigits?: number;
    compact?: boolean;
  }
): string {
  const {
    currency = "USD",
    minimumFractionDigits,
    maximumFractionDigits,
    compact = false,
  } = options ?? {};

  if (compact && Math.abs(value) >= 1_000) {
    const tiers = [
      { threshold: 1e12, suffix: "T" },
      { threshold: 1e9, suffix: "B" },
      { threshold: 1e6, suffix: "M" },
      { threshold: 1e3, suffix: "K" },
    ];
    for (const { threshold, suffix } of tiers) {
      if (Math.abs(value) >= threshold) {
        const formatted = (value / threshold).toFixed(2);
        return `$${formatted}${suffix}`;
      }
    }
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: minimumFractionDigits ?? (Math.abs(value) < 1 ? 4 : 2),
    maximumFractionDigits: maximumFractionDigits ?? (Math.abs(value) < 1 ? 6 : 2),
  }).format(value);
}

/**
 * Format a number as a percentage
 */
export function formatPercent(
  value: number,
  options?: {
    decimals?: number;
    showSign?: boolean;
  }
): string {
  const { decimals = 2, showSign = true } = options ?? {};
  const sign = showSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(decimals)}%`;
}

/**
 * Format a plain number with locale separators
 */
export function formatNumber(
  value: number,
  options?: {
    decimals?: number;
    compact?: boolean;
  }
): string {
  const { decimals, compact = false } = options ?? {};

  if (compact) {
    const tiers = [
      { threshold: 1e12, suffix: "T" },
      { threshold: 1e9, suffix: "B" },
      { threshold: 1e6, suffix: "M" },
      { threshold: 1e3, suffix: "K" },
    ];
    for (const { threshold, suffix } of tiers) {
      if (Math.abs(value) >= threshold) {
        return `${(value / threshold).toFixed(decimals ?? 1)}${suffix}`;
      }
    }
  }

  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals ?? 6,
  }).format(value);
}

/**
 * Format an ISO date string or Date object
 */
export function formatDate(
  date: string | Date,
  options?: {
    format?: "short" | "medium" | "long" | "time" | "datetime";
  }
): string {
  const { format = "medium" } = options ?? {};
  const d = typeof date === "string" ? new Date(date) : date;

  switch (format) {
    case "short":
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    case "medium":
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    case "long":
      return d.toLocaleDateString("en-US", {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric",
      });
    case "time":
      return d.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    case "datetime":
      return d.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    default:
      return d.toLocaleDateString("en-US");
  }
}

/**
 * Format a timestamp as a human-readable relative time (e.g. "3m ago")
 */
export function formatTimeAgo(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const now = Date.now();
  const diffMs = now - d.getTime();
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  const diffMonth = Math.floor(diffDay / 30);
  if (diffMonth < 12) return `${diffMonth}mo ago`;
  const diffYear = Math.floor(diffMonth / 12);
  return `${diffYear}y ago`;
}

/**
 * Format a duration in milliseconds to a human-readable string
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const min = Math.floor(sec / 60);
  const remSec = Math.floor(sec % 60);
  if (min < 60) return `${min}m ${remSec}s`;
  const hr = Math.floor(min / 60);
  const remMin = min % 60;
  if (hr < 24) return `${hr}h ${remMin}m`;
  const day = Math.floor(hr / 24);
  const remHr = hr % 24;
  return `${day}d ${remHr}h`;
}
