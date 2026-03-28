"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: React.ReactNode;
  suffix?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, icon, suffix, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-xs font-medium text-slate-400 mb-1.5"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {icon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">
              {icon}
            </div>
          )}
          <input
            id={inputId}
            ref={ref}
            className={cn(
              "w-full rounded-lg bg-dark-800 border border-white/[0.08] px-3 py-2 text-sm text-slate-200",
              "placeholder:text-slate-600",
              "transition-all duration-200",
              "hover:border-white/[0.15]",
              "focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              icon && "pl-9",
              suffix && "pr-10",
              error && "border-danger-500/50 focus:border-danger-500/50 focus:ring-danger-500/20",
              className
            )}
            {...props}
          />
          {suffix && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 text-xs">
              {suffix}
            </div>
          )}
        </div>
        {error && (
          <p className="mt-1 text-xs text-danger-400">{error}</p>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";
