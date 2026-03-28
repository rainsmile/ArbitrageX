"use client";

import React, { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: string;
  sortable?: boolean;
  align?: "left" | "center" | "right";
  width?: string;
  render?: (row: T, index: number) => React.ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T, index: number) => string;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  pagination?: {
    page: number;
    pageSize: number;
    total: number;
    onPageChange: (page: number) => void;
  };
  className?: string;
  compact?: boolean;
}

type SortDir = "asc" | "desc" | null;

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  keyExtractor,
  onRowClick,
  emptyMessage = "No data available",
  pagination,
  className,
  compact = false,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      if (sortDir === "asc") setSortDir("desc");
      else if (sortDir === "desc") {
        setSortKey(null);
        setSortDir(null);
      }
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortedData = useMemo(() => {
    if (!sortKey || !sortDir) return data;
    return [...data].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDir === "asc" ? aVal - bVal : bVal - aVal;
      }
      const aStr = String(aVal);
      const bStr = String(bVal);
      return sortDir === "asc"
        ? aStr.localeCompare(bStr)
        : bStr.localeCompare(aStr);
    });
  }, [data, sortKey, sortDir]);

  // Internal pagination: slice sortedData to the current page
  const totalItems = pagination ? pagination.total : sortedData.length;
  const totalPages = pagination
    ? Math.ceil(totalItems / pagination.pageSize)
    : 0;

  // Compute displayed page inline (no useMemo) to avoid stale-closure issues
  const displayData = (() => {
    if (!pagination) return sortedData;
    const start = (pagination.page - 1) * pagination.pageSize;
    return sortedData.slice(start, start + pagination.pageSize);
  })();

  return (
    <div className={cn("w-full overflow-hidden rounded-xl border border-white/[0.06] bg-dark-900", className)}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/[0.06]">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    "text-xs font-medium text-slate-500 uppercase tracking-wider",
                    compact ? "px-3 py-2" : "px-4 py-3",
                    col.align === "right" && "text-right",
                    col.align === "center" && "text-center",
                    col.sortable && "cursor-pointer select-none hover:text-slate-300 transition-colors"
                  )}
                  style={col.width ? { width: col.width } : undefined}
                  onClick={() => col.sortable && handleSort(col.key)}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.header}
                    {col.sortable && sortKey === col.key && (
                      <span className="text-primary-400">
                        {sortDir === "asc" ? (
                          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                            <path d="M5 2L8 7H2L5 2Z" fill="currentColor" />
                          </svg>
                        ) : (
                          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                            <path d="M5 8L2 3H8L5 8Z" fill="currentColor" />
                          </svg>
                        )}
                      </span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayData.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="py-12 text-center text-sm text-slate-600"
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              displayData.map((row, idx) => (
                <tr
                  key={keyExtractor(row, idx)}
                  className={cn(
                    "border-b border-white/[0.03] transition-colors duration-150",
                    "hover:bg-white/[0.02]",
                    onRowClick && "cursor-pointer"
                  )}
                  onClick={() => onRowClick?.(row)}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        "text-slate-300",
                        compact ? "px-3 py-2" : "px-4 py-3",
                        col.align === "right" && "text-right",
                        col.align === "center" && "text-center"
                      )}
                    >
                      {col.render
                        ? col.render(row, idx)
                        : (row[col.key] as React.ReactNode) ?? "—"}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pagination && totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-white/[0.06] px-4 py-3">
          <span className="text-xs text-slate-500">
            Page {pagination.page} of {totalPages} ({pagination.total} items)
          </span>
          <div className="flex items-center gap-1">
            <button
              className="rounded-md px-2.5 py-1 text-xs text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              disabled={pagination.page <= 1}
              onClick={() => pagination.onPageChange(pagination.page - 1)}
            >
              Previous
            </button>
            <button
              className="rounded-md px-2.5 py-1 text-xs text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              disabled={pagination.page >= totalPages}
              onClick={() => pagination.onPageChange(pagination.page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
