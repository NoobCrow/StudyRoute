import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import type { KycStatusName, PaymentState } from "../api/types";

type Tone = "ok" | "warn" | "danger" | "info" | "neutral";

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge ${tone}`} title={title}>
      {children}
    </span>
  );
}

const STATE_TONE: Record<PaymentState, Tone> = {
  DRAFT: "neutral", QUOTED: "info", PENDING_APPROVAL: "warn", APPROVED: "info", SUBMITTED: "info",
  SETTLED: "ok", REJECTED: "danger", CANCELLED: "neutral", FAILED: "danger",
};

export function StateBadge({ state }: { state: PaymentState }) {
  return <Badge tone={STATE_TONE[state]}>{state.replace("_", " ")}</Badge>;
}

const KYC_TONE: Record<KycStatusName, Tone> = { VERIFIED: "ok", PENDING: "warn", NEEDS_DOCUMENTS: "danger" };

export function KycBadge({ status }: { status: KycStatusName }) {
  return <Badge tone={KYC_TONE[status]}>KYC {status.replace("_", " ")} (simulated)</Badge>;
}

/** The yellow badge shown beside every rule that has not been checked against an official source. */
export function NotVerifiedBadge() {
  return (
    <Badge tone="warn" title="Not checked against an official source. Confirm with your AD bank.">
      Not verified
    </Badge>
  );
}

export function Notice({ tone, title, children }: { tone: "ok" | "warn" | "danger" | "info"; title?: string; children?: ReactNode }) {
  return (
    <div className={`notice ${tone}`} role={tone === "danger" ? "alert" : "status"}>
      {title ? <strong>{title}</strong> : null}
      {children}
    </div>
  );
}

export function ErrorNotice({ error }: { error: Error | null }) {
  if (!error) return null;
  if (error instanceof ApiError) {
    return (
      <Notice tone="danger" title={`${error.title} (${error.code})`}>
        <span>{error.message}</span>
        {error.retryAfter ? <span> Try again in {error.retryAfter} seconds.</span> : null}
        {error.requestId ? <span className="small muted"> Request {error.requestId}</span> : null}
      </Notice>
    );
  }
  return <Notice tone="danger" title="Something went wrong">{error.message}</Notice>;
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return <p className="muted" role="status">{what}...</p>;
}

export function PageHead({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {children ? <p>{children}</p> : null}
      </div>
      {actions ? <div className="row">{actions}</div> : null}
    </div>
  );
}

export function Field({ label, hint, error, htmlFor, children }: { label: string; hint?: string; error?: string | null; htmlFor: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint ? <span className="hint" id={`${htmlFor}-hint`}>{hint}</span> : null}
      {error ? <span className="error-text" role="alert">{error}</span> : null}
    </div>
  );
}
