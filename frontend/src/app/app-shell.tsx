"use client";

import React from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";

export function AppShell({ children }: { children: React.ReactNode }) {

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
