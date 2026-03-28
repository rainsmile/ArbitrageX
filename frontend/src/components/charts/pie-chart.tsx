"use client";

import React, { useState } from "react";
import {
  PieChart as RechartsPieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
} from "recharts";
import { cn } from "@/lib/utils";

interface PieDataPoint {
  name: string;
  value: number;
  color?: string;
}

interface DonutChartProps {
  data: PieDataPoint[];
  height?: number;
  innerRadius?: number;
  outerRadius?: number;
  centerLabel?: string;
  centerValue?: string;
  formatValue?: (value: number) => string;
  className?: string;
}

const COLORS = [
  "#3b82f6",
  "#22d3ee",
  "#4ade80",
  "#f59e0b",
  "#a78bfa",
  "#f87171",
  "#fb923c",
  "#e879f9",
];

const CustomTooltip = ({
  active,
  payload,
  formatValue,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; payload: PieDataPoint }>;
  formatValue?: (v: number) => string;
}) => {
  if (!active || !payload?.length) return null;
  const entry = payload[0];
  return (
    <div className="rounded-lg bg-dark-800 border border-white/[0.1] px-3 py-2 shadow-xl">
      <p className="text-[10px] text-slate-500 mb-0.5">{entry.name}</p>
      <p className="text-sm font-semibold font-number text-slate-200">
        {formatValue ? formatValue(entry.value) : entry.value.toLocaleString()}
      </p>
    </div>
  );
};

export function DonutChart({
  data,
  height = 250,
  innerRadius = 60,
  outerRadius = 90,
  centerLabel,
  centerValue,
  formatValue,
  className,
}: DonutChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | undefined>(undefined);

  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className={cn("w-full", className)}>
      <div className="relative">
        <ResponsiveContainer width="100%" height={height}>
          <RechartsPieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={innerRadius}
              outerRadius={outerRadius}
              paddingAngle={2}
              dataKey="value"
              onMouseEnter={(_, index) => setActiveIndex(index)}
              onMouseLeave={() => setActiveIndex(undefined)}
              stroke="none"
            >
              {data.map((entry, index) => (
                <Cell
                  key={index}
                  fill={entry.color || COLORS[index % COLORS.length]}
                  fillOpacity={activeIndex === undefined || activeIndex === index ? 1 : 0.5}
                  strokeWidth={activeIndex === index ? 2 : 0}
                  stroke={activeIndex === index ? (entry.color || COLORS[index % COLORS.length]) : "none"}
                />
              ))}
            </Pie>
            <RechartsTooltip content={<CustomTooltip formatValue={formatValue} />} />
          </RechartsPieChart>
        </ResponsiveContainer>

        {(centerLabel || centerValue) && (
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            {centerValue && (
              <span className="text-lg font-semibold text-white font-number">
                {centerValue}
              </span>
            )}
            {centerLabel && (
              <span className="text-[10px] text-slate-500 uppercase tracking-wider">
                {centerLabel}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 mt-2 px-2">
        {data.map((entry, index) => {
          const pct = total > 0 ? ((entry.value / total) * 100).toFixed(1) : "0";
          return (
            <div
              key={index}
              className="flex items-center gap-1.5 text-xs text-slate-400"
              onMouseEnter={() => setActiveIndex(index)}
              onMouseLeave={() => setActiveIndex(undefined)}
            >
              <span
                className="h-2 w-2 rounded-full shrink-0"
                style={{
                  backgroundColor:
                    entry.color || COLORS[index % COLORS.length],
                }}
              />
              <span className="truncate max-w-[80px]">{entry.name}</span>
              <span className="font-number text-slate-500">
                {formatValue ? formatValue(entry.value) : `${pct}%`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
