"use client";

import React, { useState } from "react";
import { motion, AnimatePresence, type TargetAndTransition } from "framer-motion";
import { cn } from "@/lib/utils";

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
  delay?: number;
}

const positionStyles: Record<string, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-2",
  right: "left-full top-1/2 -translate-y-1/2 ml-2",
};

const motionOrigin: Record<string, { initial: TargetAndTransition; animate: TargetAndTransition }> = {
  top: {
    initial: { opacity: 0, y: 4, scale: 0.95 },
    animate: { opacity: 1, y: 0, scale: 1 },
  },
  bottom: {
    initial: { opacity: 0, y: -4, scale: 0.95 },
    animate: { opacity: 1, y: 0, scale: 1 },
  },
  left: {
    initial: { opacity: 0, x: 4, scale: 0.95 },
    animate: { opacity: 1, x: 0, scale: 1 },
  },
  right: {
    initial: { opacity: 0, x: -4, scale: 0.95 },
    animate: { opacity: 1, x: 0, scale: 1 },
  },
};

export function Tooltip({
  content,
  children,
  side = "top",
  className,
  delay = 200,
}: TooltipProps) {
  const [open, setOpen] = useState(false);
  const timeoutRef = React.useRef<ReturnType<typeof setTimeout>>(null);

  const handleEnter = () => {
    timeoutRef.current = setTimeout(() => setOpen(true), delay);
  };

  const handleLeave = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setOpen(false);
  };

  return (
    <div
      className="relative inline-flex"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      {children}
      <AnimatePresence>
        {open && (
          <motion.div
            className={cn(
              "absolute z-50 whitespace-nowrap rounded-md px-2.5 py-1.5",
              "bg-dark-700 border border-white/[0.08] text-xs text-slate-200 shadow-xl",
              positionStyles[side],
              className
            )}
            initial={motionOrigin[side].initial}
            animate={motionOrigin[side].animate}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.15 }}
          >
            {content}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
