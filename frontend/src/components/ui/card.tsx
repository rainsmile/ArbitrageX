"use client";

import React from "react";
import { motion, type HTMLMotionProps } from "framer-motion";
import { cn } from "@/lib/utils";

interface CardProps extends Omit<HTMLMotionProps<"div">, "children"> {
  children: React.ReactNode;
  variant?: "default" | "glass" | "bordered";
  glow?: "none" | "blue" | "cyan" | "green" | "red";
  padding?: "none" | "sm" | "md" | "lg";
  hover?: boolean;
}

const glowStyles: Record<string, string> = {
  none: "",
  blue: "hover:shadow-[0_0_20px_rgba(59,130,246,0.15)]",
  cyan: "hover:shadow-[0_0_20px_rgba(6,182,212,0.15)]",
  green: "hover:shadow-[0_0_20px_rgba(34,197,94,0.15)]",
  red: "hover:shadow-[0_0_20px_rgba(239,68,68,0.15)]",
};

const paddingStyles: Record<string, string> = {
  none: "",
  sm: "p-3",
  md: "p-5",
  lg: "p-7",
};

export function Card({
  children,
  className,
  variant = "default",
  glow = "none",
  padding = "md",
  hover = false,
  ...props
}: CardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={cn(
        "rounded-xl transition-all duration-300",
        variant === "default" &&
          "bg-dark-900 border border-white/[0.06]",
        variant === "glass" &&
          "bg-dark-900/60 backdrop-blur-xl border border-white/[0.06]",
        variant === "bordered" &&
          "bg-dark-900 border border-dark-700",
        hover && "hover:border-white/[0.12] hover:bg-dark-800/80",
        glowStyles[glow],
        paddingStyles[padding],
        className
      )}
      {...props}
    >
      {children}
    </motion.div>
  );
}

interface CardHeaderProps {
  children: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
}

export function CardHeader({ children, className, action }: CardHeaderProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between border-b border-white/[0.06] pb-4 mb-4",
        className
      )}
    >
      <div className="text-sm font-medium text-slate-300">{children}</div>
      {action && <div>{action}</div>}
    </div>
  );
}

interface CardContentProps {
  children: React.ReactNode;
  className?: string;
}

export function CardContent({ children, className }: CardContentProps) {
  return <div className={cn(className)}>{children}</div>;
}
