import { Alert } from "@/components/ui/alert";

export const SANDBOX_TEXT = "Sandbox. Synthetic data, no real money moves";

/** Shown on every screen, including the sign-in page. */
export function SandboxBanner() {
  return (
    <Alert
      aria-label="Sandbox notice"
      className="border-warning-soft-foreground/20 bg-warning-soft text-warning-soft-foreground flex min-h-9 w-full flex-wrap items-center justify-center gap-x-6 gap-y-0.5 rounded-none border-0 border-b px-4 py-1.5 text-xs"
    >
      <span className="flex items-center gap-2 font-medium">
        <span className="animate-live-dot size-1.5 rounded-full bg-current" aria-hidden="true" />
        {SANDBOX_TEXT}
      </span>
      <span className="font-mono text-[11px] opacity-90">
        Indicative only. Confirm with your AD bank.
      </span>
    </Alert>
  );
}
