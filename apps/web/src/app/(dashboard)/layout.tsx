import React from "react";
import { Sidebar } from "@/components/features/layout/sidebar";
import { Header } from "@/components/features/layout/header";
import { SearchDialog } from "@/components/features/layout/search-dialog";
import { SearchHistoryProvider } from "@/contexts/SearchHistoryContext";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SearchHistoryProvider>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col overflow-hidden">
          <Header />
          <main className="flex-1 overflow-y-auto p-6">{children}</main>
        </div>
        <SearchDialog />
      </div>
    </SearchHistoryProvider>
  );
}

