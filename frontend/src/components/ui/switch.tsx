"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  description?: string;
  disabled?: boolean;
  size?: "sm" | "md";
  className?: string;
}

export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  size = "md",
  className,
}: SwitchProps) {
  const trackW = size === "sm" ? "w-8" : "w-10";
  const trackH = size === "sm" ? "h-4" : "h-5";
  const thumbSize = size === "sm" ? "h-3 w-3" : "h-4 w-4";
  const thumbTravel = size === "sm" ? 16 : 20;

  return (
    <label
      className={cn(
        "inline-flex items-center gap-3 select-none",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        className
      )}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={cn(
          "relative inline-flex shrink-0 rounded-full transition-colors duration-200",
          trackW,
          trackH,
          checked ? "bg-primary-600" : "bg-dark-700",
          !disabled && "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-dark-950"
        )}
      >
        <motion.span
          className={cn(
            "block rounded-full bg-white shadow-sm",
            thumbSize,
            "mt-0.5 ml-0.5"
          )}
          animate={{ x: checked ? thumbTravel : 0 }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        />
        {checked && (
          <span className="absolute inset-0 rounded-full bg-primary-400/20 blur-sm" />
        )}
      </button>
      {(label || description) && (
        <div className="flex flex-col">
          {label && (
            <span className="text-sm text-slate-200">{label}</span>
          )}
          {description && (
            <span className="text-xs text-slate-500">{description}</span>
          )}
        </div>
      )}
    </label>
  );
}
