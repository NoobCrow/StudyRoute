"use client";

import { LogOut, Monitor, Moon, Search, Sparkles, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { NAV } from "@/components/layout/nav";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";

/** Search or jump to a screen with Ctrl or Cmd + K. */
export function CommandMenu({ onAskAssistant }: { onAskAssistant: () => void }) {
  const [open, setOpen] = useState(false);
  const { user, logout } = useAuth();
  const { setTheme } = useTheme();
  const router = useRouter();

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((value) => !value);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function run(action: () => void) {
    setOpen(false);
    action();
  }

  const items = NAV.filter((item) => user && item.roles.includes(user.role));

  return (
    <>
      <Button
        type="button"
        variant="outline"
        className="bg-card text-muted-foreground hidden h-9 w-56 justify-start gap-2 px-3 font-normal shadow-none md:inline-flex"
        onClick={() => setOpen(true)}
        aria-label="Search or jump to a screen"
      >
        <Search aria-hidden="true" />
        <span className="flex-1 text-left">Search or jump to</span>
        <kbd
          className="bg-muted rounded px-1.5 py-0.5 font-mono text-[10px]"
          title="Command or Control + K"
        >
          ⌘K
        </kbd>
      </Button>
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="bg-card md:hidden"
        onClick={() => setOpen(true)}
        aria-label="Search or jump to a screen"
      >
        <Search aria-hidden="true" />
      </Button>
      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Search or jump to"
        description="Go to a screen or change the theme"
      >
        <CommandInput placeholder="Search or jump to..." />
        <CommandList>
          <CommandEmpty>Nothing found.</CommandEmpty>
          <CommandGroup heading="Go to">
            {items.map((item) => (
              <CommandItem key={item.href} onSelect={() => run(() => router.push(item.href))}>
                <item.icon aria-hidden="true" />
                {item.label}
              </CommandItem>
            ))}
          </CommandGroup>
          {user && user.role !== "admin" ? (
            <CommandGroup heading="Assistant">
              <CommandItem onSelect={() => run(onAskAssistant)}>
                <Sparkles aria-hidden="true" />
                Ask the assistant
              </CommandItem>
            </CommandGroup>
          ) : null}
          <CommandSeparator />
          <CommandGroup heading="Theme">
            <CommandItem onSelect={() => run(() => setTheme("light"))}>
              <Sun aria-hidden="true" />
              Light
            </CommandItem>
            <CommandItem onSelect={() => run(() => setTheme("dark"))}>
              <Moon aria-hidden="true" />
              Dark
            </CommandItem>
            <CommandItem onSelect={() => run(() => setTheme("system"))}>
              <Monitor aria-hidden="true" />
              System
            </CommandItem>
          </CommandGroup>
          <CommandSeparator />
          <CommandGroup heading="Account">
            <CommandItem
              onSelect={() =>
                run(() => {
                  void logout().then(() => router.replace("/login/"));
                })
              }
            >
              <LogOut aria-hidden="true" />
              Sign out
              <CommandShortcut>session</CommandShortcut>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}
