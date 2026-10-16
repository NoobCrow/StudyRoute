"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState, type ReactNode } from "react";

import { AuthProvider } from "@/components/providers/auth-provider";
import { ClientOnly } from "@/components/providers/client-only";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      // Errors are shown on the card with a Retry button, so no silent automatic retries.
      queries: { retry: false, refetchOnWindowFocus: false, staleTime: 15_000 },
      mutations: { retry: false },
    },
  });
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient);
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem storageKey="sr.theme">
      <ClientOnly>
        <QueryClientProvider client={client}>
          <AuthProvider>
            <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
            <Toaster position="bottom-right" />
          </AuthProvider>
        </QueryClientProvider>
      </ClientOnly>
    </ThemeProvider>
  );
}
