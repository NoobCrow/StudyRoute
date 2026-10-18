"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { StateBadge } from "@/components/app/status";
import { KycCard } from "@/components/dashboard/kyc-card";
import { MfaDialog } from "@/components/payment/mfa-dialog";
import { Mt103Card, SummaryCard, TrackerCard } from "@/components/payment/payment-panels";
import { ParentReviewPanel } from "@/components/review/parent-review-panel";
import { ReviewerBriefCard } from "@/components/review/reviewer-brief";
import { SecurityDemo, type ApproveAttempt } from "@/components/payment/security-demo";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useChatScope } from "@/hooks/use-chat-scope";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { post } from "@/lib/api/client";
import { loadHealth } from "@/lib/api/health";
import type { ApprovalRequested, Mt103Preview, Payment, Quote, Tracker } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";

type ActionName = "request" | "approve" | "reject" | "cancel" | "requote";

function isLive(data: Payment | undefined): boolean {
  if (!data) return false;
  const codes = new Set(data.readiness.blockers.map((b) => b.code));
  return (
    data.state === "APPROVED" ||
    data.state === "SUBMITTED" ||
    codes.has("KYC_NOT_VERIFIED") ||
    codes.has("QUOTE_EXPIRED")
  );
}

export function PaymentScreen() {
  const paymentId = useSearchParams().get("id") ?? "";
  const { user } = useAuth();
  const payment = useApi<Payment>(paymentId ? `/payments/${paymentId}` : null, {
    refetchInterval: (data) => (isLive(data as Payment | undefined) ? 2500 : false),
  });
  const tracker = useApi<Tracker>(paymentId ? `/payments/${paymentId}/tracker` : null);
  const preview = useApi<Mt103Preview>(
    paymentId ? `/payments/${paymentId}/instruction-preview` : null,
  );
  const data = payment.data;

  const [busy, setBusy] = useState<ActionName | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [mfaOpen, setMfaOpen] = useState(false);
  const [attempt, setAttempt] = useState<ApproveAttempt | null>(null);
  const [sandbox, setSandbox] = useState<{ code: string; on: boolean }>({ code: "", on: false });

  const stamp = `${paymentId}:${data?.state ?? ""}:${data?.quote_id ?? ""}:${data?.summary_hash ?? ""}`;
  const requestKey = useIdempotencyKey(`request:${stamp}`);
  const approveKey = useIdempotencyKey(`approve:${stamp}`);
  const rejectKey = useIdempotencyKey(`reject:${stamp}`);
  const cancelKey = useIdempotencyKey(`cancel:${stamp}`);
  const requoteKey = useIdempotencyKey(`requote:${stamp}`);

  useChatScope({ paymentId: paymentId || undefined, quoteId: data?.quote_id });
  useEffect(() => {
    loadHealth()
      .then((h) => setSandbox({ code: h.demo?.mfa_code ?? "", on: h.mode === "sandbox" }))
      .catch(() => undefined);
  }, []);

  const { reload: reloadTracker } = tracker;
  const updatedAt = data?.updated_at;
  useEffect(() => {
    if (updatedAt) reloadTracker();
  }, [updatedAt, reloadTracker]);

  const refreshAll = () => {
    payment.reload();
    tracker.reload();
    preview.reload();
  };

  async function run(name: ActionName, work: () => Promise<unknown>) {
    setBusy(name);
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(null);
      refreshAll();
    }
  }

  if (!user) return null;
  if (!paymentId) {
    return (
      <div className="space-y-4">
        <Notice tone="warn">Choose a payment from the list.</Notice>
        <Link href="/payments/" className="text-primary hover:underline">
          Back to payments
        </Link>
      </div>
    );
  }
  if (payment.loading && !data) return <CardSkeleton lines={6} label="Loading the payment" />;
  if (!data) {
    return (
      <div className="space-y-4">
        <ErrorNotice error={payment.error} onRetry={payment.reload} />
        <Link href="/payments/" className="text-primary hover:underline">
          Back to payments
        </Link>
      </div>
    );
  }

  const can = (permission: string) => user.permissions.includes(permission);
  const state = data.state;
  const base = `/payments/${data.payment_id}`;
  const blockers = data.readiness.blockers;

  const requestApproval = () =>
    run("request", () =>
      post<ApprovalRequested>(`${base}/request-approval`, {}, { idempotencyKey: requestKey }),
    );
  const reject = () =>
    run("reject", () =>
      post(
        `${base}/reject`,
        { reason: "Rejected at the approval stage" },
        { idempotencyKey: rejectKey },
      ),
    );
  const cancel = () =>
    run("cancel", () => post(`${base}/cancel`, {}, { idempotencyKey: cancelKey }));
  const approveWith = (proof: string) => {
    setMfaOpen(false);
    const hash = data.summary_hash ?? "";
    void run("approve", async () => {
      await post(
        `${base}/approve`,
        { confirm_summary_hash: hash },
        { idempotencyKey: approveKey, mfaProof: proof },
      );
      setAttempt({ idempotencyKey: approveKey, mfaProof: proof, confirmSummaryHash: hash });
    });
  };
  const requote = () =>
    run("requote", async () => {
      const fresh = await post<Quote>("/quotes", {
        target: { amount_minor: data.target.amount_minor, currency: data.target.currency },
        purpose: data.purpose,
        destination_country: data.destination_country,
        charge_code: data.result.requested_charge_code,
        recipient_id: data.recipient.recipient_id,
        due_date: data.due_date ?? undefined,
      });
      await post(
        `${base}/requote`,
        { quote_id: fresh.quote_id, provider_id: data.provider_id },
        { idempotencyKey: requoteKey },
      );
    });

  const terminal = ["SETTLED", "REJECTED", "CANCELLED", "FAILED"].includes(state);
  const open = ["DRAFT", "QUOTED", "PENDING_APPROVAL"].includes(state);
  const idle = busy !== null;

  return (
    <div className="space-y-6">
      <PageHead title={`Payment to ${data.recipient.label}`} actions={<StateBadge state={state} />}>
        {data.target.formatted} for {data.purpose.toLowerCase()} via {data.provider_name}.
        Simulated: no real money moves.
      </PageHead>
      <ErrorNotice error={error} />

      {state === "DRAFT" ? (
        <Notice tone="warn" title="This payment needs a fresh quote">
          The earlier quote expired, so the payment went back to draft. Get a new quote from the
          same provider to continue.
        </Notice>
      ) : null}
      {data.failure_reason ? (
        <Notice tone="danger" title="The payment did not complete">
          {data.failure_reason}
        </Notice>
      ) : null}
      {state === "SETTLED" ? (
        <Notice tone="ok" title="Settled (simulated)">
          The simulated provider credited the beneficiary.
        </Notice>
      ) : null}

      <SummaryCard payment={data} />

      {blockers.length > 0 ? (
        <Card aria-labelledby="blockers-title">
          <CardHeader>
            <CardTitle id="blockers-title" className="text-base">
              Before this can be approved
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1.5 pl-5">
              {blockers.map((b) => (
                <li key={b.code}>
                  <strong className="font-medium">{b.message}</strong>
                  {b.code === "RECIPIENT_NOT_ALLOWLISTED" ? (
                    <>
                      {" "}
                      <Link href="/recipients/" className="text-primary underline">
                        Open recipients
                      </Link>
                      .
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
      {open && user.role !== "admin" ? <KycCard /> : null}
      {data.state !== "DRAFT" && data.state !== "QUOTED" ? (
        user.role === "admin" ? (
          <ReviewerBriefCard
            paymentId={data.payment_id}
            sandboxCode={sandbox.code || undefined}
            onDecided={refreshAll}
          />
        ) : (
          <ParentReviewPanel paymentId={data.payment_id} />
        )
      ) : null}

      <Card aria-labelledby="actions-title">
        <CardHeader>
          <CardTitle id="actions-title" className="text-base">
            Actions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {state === "DRAFT" && can("payments:draft") ? (
              <Button
                type="button"
                loading={busy === "requote"}
                disabled={idle}
                onClick={() => void requote()}
              >
                Get a fresh quote
              </Button>
            ) : null}
            {state === "QUOTED" && can("payments:request_approval") ? (
              <Button
                type="button"
                loading={busy === "request"}
                disabled={idle || !data.readiness.can_request_approval}
                onClick={() => void requestApproval()}
              >
                Request approval
              </Button>
            ) : null}
            {state === "PENDING_APPROVAL" && can("payments:approve") ? (
              <Button
                type="button"
                disabled={idle || !data.readiness.can_approve}
                onClick={() => setMfaOpen(true)}
              >
                Approve with MFA
              </Button>
            ) : null}
            {state === "PENDING_APPROVAL" && can("payments:reject") ? (
              <Button
                type="button"
                variant="destructive-outline"
                loading={busy === "reject"}
                disabled={idle}
                onClick={() => void reject()}
              >
                Reject
              </Button>
            ) : null}
            {["DRAFT", "QUOTED", "PENDING_APPROVAL", "APPROVED"].includes(state) &&
            can("payments:cancel") ? (
              <Button
                type="button"
                variant="outline"
                loading={busy === "cancel"}
                disabled={idle}
                onClick={() => void cancel()}
              >
                Cancel payment
              </Button>
            ) : null}
            <Button asChild variant="outline">
              <Link href={`/audit/?payment_id=${data.payment_id}`}>See its audit trail</Link>
            </Button>
            {can("audit:read") ? (
              <Button asChild variant="outline">
                <Link href={`/payments/report/?id=${data.payment_id}`}>Compliance report</Link>
              </Button>
            ) : null}
          </div>
          {terminal ? (
            <p className="text-muted-foreground text-sm">
              This payment is finished and cannot change.
            </p>
          ) : null}
          {!terminal && !can("payments:approve") && user.role !== "admin" ? (
            <p className="text-muted-foreground text-sm">
              Only the paying parent can request approval and approve. Approval always needs a fresh
              MFA code.
            </p>
          ) : null}
          {state === "PENDING_APPROVAL" && !data.readiness.can_approve && blockers.length > 0 ? (
            <p className="text-muted-foreground text-sm">
              Approval is disabled until the items above are resolved.
            </p>
          ) : null}
          <p className="text-muted-foreground text-xs">
            Every payment needs your authorization with a fresh MFA code, whatever its risk score.
            The assistant can suggest these steps but can never take them. {data.disclaimer}
          </p>
        </CardContent>
      </Card>

      <div className="grid items-start gap-6 xl:grid-cols-[1.3fr_1fr]">
        {preview.data ? (
          <Mt103Card preview={preview.data} />
        ) : (
          <CardSkeleton lines={4} label="Preparing the instruction preview" />
        )}
        {tracker.data ? (
          <TrackerCard tracker={tracker.data} />
        ) : (
          <CardSkeleton lines={4} label="Loading the tracker" />
        )}
      </div>

      {sandbox.on && can("payments:approve") ? (
        <SecurityDemo payment={data} attempt={attempt} />
      ) : null}

      {mfaOpen ? (
        <MfaDialog
          title="Approve this payment"
          scope="approve_payment"
          subjectId={data.payment_id}
          sandboxCode={sandbox.code || undefined}
          onProof={approveWith}
          onCancel={() => setMfaOpen(false)}
        />
      ) : null}
    </div>
  );
}
