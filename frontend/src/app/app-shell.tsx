"use client";

import React, { useEffect } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { useAlertStore, useSettingsStore, useSystemStore } from "@/store";
import {
  mockAlerts,
  mockExchanges,
  mockSystemHealth,
  mockSystemMetrics,
  mockStrategies,
  mockRiskRules,
} from "@/lib/mock-data";

export function AppShell({ children }: { children: React.ReactNode }) {
  // Hydrate stores with mock data on mount
  useEffect(() => {
    const alertStore = useAlertStore.getState();
    alertStore.setAlerts(mockAlerts);

    const settingsStore = useSettingsStore.getState();
    settingsStore.setStrategies(mockStrategies);
    settingsStore.setRiskRules(mockRiskRules);

    const systemStore = useSystemStore.getState();
    systemStore.setExchanges(mockExchanges);
    systemStore.setHealth(mockSystemHealth);
    systemStore.setMetrics(mockSystemMetrics);
  }, []);

  return (
    <div className="flex h-screen bg-[#0a0e1a] text-gray-100 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto overflow-x-hidden p-4 lg:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
