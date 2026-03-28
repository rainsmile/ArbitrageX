"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface Tab {
  id: string;
  label: string;
  icon?: React.ReactNode;
  count?: number;
}

interface TabsProps {
  tabs: Tab[];
  activeTab?: string;
  onChange?: (tabId: string) => void;
  className?: string;
  children?: React.ReactNode;
}

export function Tabs({
  tabs,
  activeTab: controlledActive,
  onChange,
  className,
}: TabsProps) {
  const [internalActive, setInternalActive] = useState(tabs[0]?.id ?? "");
  const activeTab = controlledActive ?? internalActive;

  const handleChange = (tabId: string) => {
    if (onChange) {
      onChange(tabId);
    } else {
      setInternalActive(tabId);
    }
  };

  return (
    <div
      className={cn(
        "flex items-center gap-0.5 border-b border-white/[0.06]",
        className
      )}
    >
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => handleChange(tab.id)}
            className={cn(
              "relative flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors duration-200",
              "focus-visible:outline-none",
              isActive
                ? "text-slate-100"
                : "text-slate-500 hover:text-slate-300"
            )}
          >
            {tab.icon && (
              <span className="shrink-0 [&>svg]:h-4 [&>svg]:w-4">
                {tab.icon}
              </span>
            )}
            {tab.label}
            {tab.count !== undefined && (
              <span
                className={cn(
                  "ml-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                  isActive
                    ? "bg-primary-500/20 text-primary-400"
                    : "bg-dark-700 text-slate-500"
                )}
              >
                {tab.count}
              </span>
            )}
            {isActive && (
              <motion.div
                layoutId="tab-underline"
                className="absolute bottom-0 left-0 right-0 h-[2px] bg-primary-500"
                transition={{ type: "spring", stiffness: 500, damping: 35 }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}

interface TabPanelProps {
  tabId: string;
  activeTab: string;
  children: React.ReactNode;
  className?: string;
}

export function TabPanel({
  tabId,
  activeTab,
  children,
  className,
}: TabPanelProps) {
  if (tabId !== activeTab) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
