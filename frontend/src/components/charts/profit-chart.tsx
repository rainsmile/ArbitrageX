"use client";

import React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from "recharts";
import { cn } from "@/lib/utils";

interface ProfitDataPoint {
  time: string;
  value: number;
  [key: string]: unknown;
}

interface ProfitChartProps {
  data: ProfitDataPoint[];
  dataKey?: string;
  height?: number;
  showGrid?: boolean;
  showAxis?: boolean;
  color?: "cyan" | "green" | "blue";
  formatValue?: (value: number) => string;
  formatTime?: (time: string) => string;
  className?: string;
}

const colorConfig = {
  cyan: { stroke: "#22d3ee", fill: "url(#gradientCyan)" },
  green: { stroke: "#4ade80", fill: "url(#gradientGreen)" },
  blue: { stroke: "#60a5fa", fill: "url(#gradientBlue)" },
};

const CustomTooltip = ({
  active,
  payload,
  label,
  formatValue,
  formatTime,
}: {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
  formatValue?: (v: number) => string;
  formatTime?: (t: string) => string;
}) => {
  if (!active || !payload?.length) return null;
  const val = payload[0].value;
  return (
    <div className="rounded-lg bg-dark-800 border border-white/[0.1] px-3 py-2 shadow-xl">
      <p className="text-[10px] text-slate-500 mb-0.5">
        {formatTime ? formatTime(String(label)) : label}
      </p>
      <p className={cn("text-sm font-semibold font-number", val >= 0 ? "text-success-400" : "text-danger-400")}>
        {formatValue ? formatValue(val) : `$${val.toLocaleString()}`}
      </p>
    </div>
  );
};

export function ProfitChart({
  data,
  dataKey = "value",
  height = 300,
  showGrid = true,
  showAxis = true,
  color = "cyan",
  formatValue,
  formatTime,
  className,
}: ProfitChartProps) {
  const { stroke, fill } = colorConfig[color];

  return (
    <div className={cn("w-full", className)}>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gradientCyan" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gradientGreen" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#4ade80" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#4ade80" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gradientBlue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#60a5fa" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#60a5fa" stopOpacity={0} />
            </linearGradient>
          </defs>
          {showGrid && (
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.04)"
              vertical={false}
            />
          )}
          {showAxis && (
            <>
              <XAxis
                dataKey="time"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#64748b", fontSize: 10 }}
                tickFormatter={formatTime}
                dy={8}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#64748b", fontSize: 10 }}
                tickFormatter={(v: number) =>
                  formatValue ? formatValue(v) : `$${v.toLocaleString()}`
                }
                dx={-4}
                width={60}
              />
            </>
          )}
          <RechartsTooltip
            content={
              <CustomTooltip
                formatValue={formatValue}
                formatTime={formatTime}
              />
            }
            cursor={{
              stroke: "rgba(255,255,255,0.1)",
              strokeWidth: 1,
            }}
          />
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={stroke}
            strokeWidth={2}
            fill={fill}
            dot={false}
            activeDot={{
              r: 4,
              stroke,
              strokeWidth: 2,
              fill: "#0f1419",
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
