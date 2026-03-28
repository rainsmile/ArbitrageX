"use client";

import React from "react";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  YAxis,
} from "recharts";
import { cn } from "@/lib/utils";

interface MiniChartProps {
  data: number[];
  width?: number;
  height?: number;
  color?: "green" | "red" | "cyan" | "blue" | "auto";
  className?: string;
}

const colorMap: Record<string, string> = {
  green: "#4ade80",
  red: "#f87171",
  cyan: "#22d3ee",
  blue: "#60a5fa",
};

export function MiniChart({
  data,
  width = 80,
  height = 32,
  color = "auto",
  className,
}: MiniChartProps) {
  if (data.length < 2) return null;

  const chartData = data.map((value, index) => ({ index, value }));
  const trend = data[data.length - 1] >= data[0];
  const strokeColor =
    color === "auto"
      ? trend
        ? "#4ade80"
        : "#f87171"
      : colorMap[color];

  const min = Math.min(...data);
  const max = Math.max(...data);
  const padding = (max - min) * 0.1 || 1;

  return (
    <div className={cn("inline-flex", className)} style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <YAxis
            domain={[min - padding, max + padding]}
            hide
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={strokeColor}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
