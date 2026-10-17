"use client";

import { useState, type ReactNode } from "react";

import { useAuth } from "@/components/providers/auth-provider";
import { AssistantProvider } from "@/components/assistant/assistant-context";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AssistantSheet } from "@/components/layout/assistant-sheet";
import { Topbar } from "@/components/layout/topbar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

/** The signed-in frame: sidebar, top bar, page and the assistant side sheet. */
export function AppShell({ children }: { children: ReactNode }) {
  const [assistantOpen, setAssistantOpen] = useState(false);
  const { user } = useAuth();
  return (
    <AssistantProvider key={user?.user_id ?? "signed-out"}>
      <SidebarProvider
        className="min-h-[calc(100svh-2.25rem)]"
        style={{ "--sidebar-width": "15.25rem" } as React.CSSProperties}
      >
        <a
          href="#main"
          className="bg-primary text-primary-foreground sr-only z-50 rounded-md px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
        >
          Skip to content
        </a>
        <AppSidebar />
        <SidebarInset className="bg-background min-w-0">
          <Topbar onAskAssistant={() => setAssistantOpen(true)} />
          <main
            id="main"
            tabIndex={-1}
            className="mx-auto w-full max-w-[70rem] flex-1 space-y-6 px-4 py-6 outline-none md:px-8 md:py-8"
          >
            {children}
          </main>
        </SidebarInset>
        <AssistantSheet open={assistantOpen} onOpenChange={setAssistantOpen} />
      </SidebarProvider>
    </AssistantProvider>
  );
}
