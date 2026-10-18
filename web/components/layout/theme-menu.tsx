"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const LABEL = { light: "Light", dark: "Dark", system: "System" } as const;

/** Light, dark or follow the system. The choice is remembered in this browser only. */
export function ThemeMenu() {
  const { theme = "system", setTheme } = useTheme();
  const key = theme === "light" || theme === "dark" ? theme : "system";
  const Icon = key === "dark" ? Moon : key === "light" ? Sun : Monitor;
  /** Colours cross-fade for a moment instead of snapping. */
  function change(next: string) {
    const root = document.documentElement;
    root.classList.add("theme-fade");
    setTheme(next);
    window.setTimeout(() => root.classList.remove("theme-fade"), 450);
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="text-muted-foreground h-8 gap-1.5 px-2">
          <Icon aria-hidden="true" />
          <span>Theme: {LABEL[key]}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-40">
        <DropdownMenuRadioGroup value={key} onValueChange={change}>
          <DropdownMenuRadioItem value="light">Light</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">Dark</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">System</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
