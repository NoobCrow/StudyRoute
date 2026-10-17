"use client";

import { toast } from "sonner";

import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { BrandMark } from "@/components/layout/brand-mark";
import { NAV, isActive } from "@/components/layout/nav";
import { ThemeMenu } from "@/components/layout/theme-menu";
import { useAuth } from "@/components/providers/auth-provider";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function AppSidebar() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const { setOpenMobile } = useSidebar();
  if (!user) return null;
  const items = NAV.filter((item) => item.roles.includes(user.role));

  async function signOut() {
    try {
      await logout();
      router.replace("/login/");
    } catch {
      toast.error("Sign out failed. Check your connection and try again.");
    }
  }

  return (
    <Sidebar collapsible="icon" className="top-9 h-[calc(100svh-2.25rem)]">
      <SidebarHeader className="px-3 py-4">
        <Link
          href="/"
          aria-label="StudyRoute home"
          className="focus-visible:ring-sidebar-ring flex items-center gap-2.5 rounded-md px-1 font-semibold tracking-tight outline-none focus-visible:ring-2"
        >
          <BrandMark className="size-8 shrink-0" />
          <span className="text-base group-data-[collapsible=icon]:hidden">StudyRoute</span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label="Main">
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu className="stagger">
                {items.map((item) => (
                  <SidebarMenuItem key={item.href} className="animate-rise">
                    <SidebarMenuButton
                      asChild
                      isActive={isActive(pathname, item.href)}
                      tooltip={item.label}
                      className="data-[active=true]:bg-card before:bg-primary data-[active=true]:[&>svg]:text-primary relative h-9 transition-all duration-200 hover:translate-x-0.5 data-[active=true]:border data-[active=true]:shadow-xs data-[active=true]:before:absolute data-[active=true]:before:top-1.5 data-[active=true]:before:bottom-1.5 data-[active=true]:before:left-0 data-[active=true]:before:w-[3px] data-[active=true]:before:rounded-full [&>svg]:transition-transform [&>svg]:duration-200 hover:[&>svg]:scale-110"
                    >
                      <Link
                        href={item.href}
                        aria-current={isActive(pathname, item.href) ? "page" : undefined}
                        onClick={() => setOpenMobile(false)}
                      >
                        <item.icon aria-hidden="true" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </nav>
      </SidebarContent>
      <SidebarFooter className="gap-1 border-t px-3 py-3">
        <div className="flex items-center gap-2.5 px-1">
          <Avatar className="size-8">
            <AvatarFallback className="bg-success-soft text-success-soft-foreground text-xs font-semibold">
              {initials(user.display_name)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 leading-tight group-data-[collapsible=icon]:hidden">
            <p className="truncate text-sm font-medium">{user.display_name}</p>
            <p className="text-muted-foreground text-xs">{user.role}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-1 group-data-[collapsible=icon]:hidden">
          <ThemeMenu />
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground h-8 gap-1.5 px-2"
            onClick={() => void signOut()}
          >
            <LogOut aria-hidden="true" />
            Sign out
          </Button>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
