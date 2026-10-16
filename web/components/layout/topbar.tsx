"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { CommandMenu } from "@/components/layout/command-menu";
import { trailFor } from "@/components/layout/nav";
import { useAuth } from "@/components/providers/auth-provider";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";

export function Topbar({ onAskAssistant }: { onAskAssistant: () => void }) {
  const pathname = usePathname();
  const { user } = useAuth();
  const trail = trailFor(pathname);
  return (
    <header className="bg-background/90 sticky top-9 z-20 flex h-14 shrink-0 items-center gap-3 border-b px-4 backdrop-blur md:px-8">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="h-5" />
      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="flex-nowrap">
          <BreadcrumbItem className="hidden sm:inline-flex">
            <BreadcrumbLink asChild>
              <Link href="/">StudyRoute</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          {trail.map((part, index) => (
            <Fragment key={part}>
              <BreadcrumbSeparator className="hidden sm:block" />
              <BreadcrumbItem>
                {index === trail.length - 1 ? (
                  <BreadcrumbPage>{part}</BreadcrumbPage>
                ) : (
                  <span>{part}</span>
                )}
              </BreadcrumbItem>
            </Fragment>
          ))}
        </BreadcrumbList>
      </Breadcrumb>
      <CommandMenu onAskAssistant={onAskAssistant} />
      {user && user.role !== "admin" ? (
        <Button type="button" variant="outline" className="bg-card gap-2" onClick={onAskAssistant}>
          <Sparkles aria-hidden="true" />
          <span className="hidden sm:inline">Ask the assistant</span>
          <span className="sr-only sm:hidden">Ask the assistant</span>
        </Button>
      ) : null}
    </header>
  );
}
