import type { ComponentProps } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { KycStatusName, PaymentState } from "@/lib/api/types";

export type Tone = "ok" | "warn" | "danger" | "info" | "neutral";

const VARIANT = {
  ok: "success",
  warn: "warning",
  danger: "danger",
  info: "info",
  neutral: "muted",
} as const;

/** A status chip. `tone` keeps the vocabulary of the old UI: ok, warn, danger, info, neutral. */
export function Chip({
  tone = "neutral",
  children,
  className,
  ...props
}: { tone?: Tone } & Omit<ComponentProps<typeof Badge>, "variant">) {
  return (
    <Badge variant={VARIANT[tone]} className={cn("animate-pop", className)} {...props}>
      {children}
    </Badge>
  );
}

const STATE_TONE: Record<PaymentState, Tone> = {
  DRAFT: "neutral",
  QUOTED: "info",
  PENDING_APPROVAL: "warn",
  APPROVED: "info",
  SUBMITTED: "info",
  SETTLED: "ok",
  REJECTED: "danger",
  CANCELLED: "neutral",
  FAILED: "danger",
};

export function StateBadge({ state }: { state: PaymentState }) {
  return <Chip tone={STATE_TONE[state]}>{state.replace("_", " ")}</Chip>;
}

const KYC_TONE: Record<KycStatusName, Tone> = {
  VERIFIED: "ok",
  PENDING: "warn",
  NEEDS_DOCUMENTS: "danger",
};

export function KycBadge({ status }: { status: KycStatusName }) {
  return (
    <Chip tone={KYC_TONE[status]}>KYC {status.replace("_", " ").toLowerCase()} (simulated)</Chip>
  );
}

/** The yellow badge shown beside every rule that has not been checked against an official source. */
export function NotVerifiedBadge() {
  return (
    <Chip tone="warn" title="Not checked against an official source. Confirm with your AD bank.">
      Not verified
    </Chip>
  );
}
