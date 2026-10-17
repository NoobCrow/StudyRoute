"use client";

import { Check, Copy } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";

/** Copies a reference (a UETR, an id) and says so: the icon turns into a tick for two seconds. */
export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      return; // Clipboard access can be refused (insecure page, permissions): then nothing claims success.
    }
    setCopied(true);
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      aria-label={copied ? `${label} copied` : `Copy ${label}`}
      onClick={() => void copy()}
    >
      {copied ? (
        <Check key="done" aria-hidden="true" className="animate-tick text-primary" />
      ) : (
        <Copy key="copy" aria-hidden="true" />
      )}
    </Button>
  );
}
