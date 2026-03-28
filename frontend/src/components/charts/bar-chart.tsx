"use client";

import React from "react";
import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { cn } from "@/lib/utils";

interface BarDataPoint {
  name: string;
  value: number;
  [key: string]: unknown;
}

interface BarChartProps {
  data: BarDataPoint[];
  dataKey?: string;
  height?: number;
  color?: string;
  colorByValue?: boolean;
  showGrid?: boolean;
  layout?: "vertical" | "horizontal";
  formatValue?: (value: number) => string;
  className?: string;
}

const CustomTooltip = ({
  active,
  payload,
  label,
  formatValue,
}: {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
  formatValue?: (v: number) => string;
}) => {
  if (!active || !payload?.length) return null;
  const val = payload[0].value;
  return (
    <div className="rounded-lg bg-dark-800 border border-white/[0.1] px-3 py-2 shadow-xl">
      <p className="text-[10px] text-slate-500 mb-0.5">{label}</p>
      <p className="text-sm font-semibold font-number text-slate-200">
        {formatValue ? formatValue(val) : val.toLocaleString()}
      </p>
    </div>
  );
};

export function BarChartComponent({
  data,
  dataKey = "value",
  height = 300,
  color = "#3b82f6",
  colorByValue = false,
  showGrid = true,
  layout = "horizontal",
  formatValue,
  className,
}: BarChartProps) {
  return (
    <div className={cn("w-full", className)}>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsBarChart
          data={data}
          layout={layout === "vertical" ? "vertical" : "horizontal"}
          margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
        >
          {showGrid && (
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.04)"
              vertical={layout === "vertical"}
              horizontal={layout === "horizontal"}
            />
          )}
          {layout === "horizontal" ? (
            <>
              <XAxis
                dataKey="name"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#64748b", fontSize: 10 }}
                dy={8}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#64748b", fontSize: 10 }}
                tickFormatter={(v: number) =>
                  formatValue ? formatValue(v) : v.toLocaleString()
                }
                width={60}
              />
            </>
          ) : (
            <>
              <XAxis
                type="number"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#64748b", fontSize: 10 }}
                tickFormatter={(v: number) =>
                  formatValue ? formatValue(v) : v.toLocaleString()
                }
              />
              <YAxis
                type="category"
                dataKey="name"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#64748b", fontSize: 10 }}
                width={80}
              />
            </>
          )}
          <RechartsTooltip
            content={<CustomTooltip formatValue={formatValue} />}
            cursor={{ fill: "rgba(255,255,255,0.03)" }}
          />
          <Bar
            dataKey={dataKey}
            radius={[4, 4, 0, 0]}
            maxBarSize={40}
          >
            {data.map((entry, index) => (
              <Cell
                key={index}
                fill={
                  colorByValue
                    ? entry.value >= 0
                      ? "#4ade80"
                      : "#f87171"
                    : color
                }
                fillOpacity={0.8}
              />
            ))}
          </Bar>
        </RechartsBarChart>
      </ResponsiveContainer>
    </div>
  );
}
