"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  options: SelectOption[];
  label?: string;
  error?: string;
  placeholder?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, options, label, error, placeholder, id, ...props }, ref) => {
    const selectId = id || label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className={cn("inline-block", className)}>
        {label && (
          <label
            htmlFor={selectId}
            className="block text-xs font-medium text-slate-400 mb-1.5"
          >
            {label}
          </label>
        )}
        <div className="relative">
          <select
            id={selectId}
            ref={ref}
            className={cn(
              "w-full appearance-none rounded-lg bg-dark-800 border border-white/[0.08] px-3 py-2 pr-8 text-sm text-slate-200",
              "transition-all duration-200",
              "hover:border-white/[0.15]",
              "focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              error && "border-danger-500/50",
            )}
            {...props}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <div className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500">
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="none"
            >
              <path
                d="M3 4.5L6 7.5L9 4.5"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
        </div>
        {error && (
          <p className="mt-1 text-xs text-danger-400">{error}</p>
        )}
      </div>
    );
  }
);

Select.displayName = "Select";
