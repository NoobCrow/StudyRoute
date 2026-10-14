import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { get, post } from "../api/client";
import type { ApprovalRequested, Mt103Preview, Payment, Quote, Tracker } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useChatScope } from "../chatContext";
import { KycCard } from "../components/KycCard";
import { MfaDialog } from "../components/MfaDialog";
import { Mt103Card, SummaryCard, TrackerCard } from "../components/PaymentPanels";
import { SecurityDemo } from "../components/SecurityDemo";
import type { ApproveAttempt } from "../components/SecurityDemo";
import { ErrorNotice, Loading, Notice, PageHead, StateBadge } from "../components/Ui";
import { loadHealth } from "../health";
import { useAsync, usePolling } from "../hooks";
import { useIdempotencyKey } from "../idempotency";

type ActionName = "request" | "approve" | "reject" | "cancel" | "requote";

export function PaymentScreen() {
  const { paymentId = "" } = useParams();
  const { user } = useAuth();
  const payment = useAsync(() => get<Payment>(`/payments/${paymentId}`), [paymentId]);
  const tracker = useAsync(() => get<Tracker>(`/payments/${paymentId}/tracker`), [paymentId]);
  const preview = useAsync(() => get<Mt103Preview>(`/payments/${paymentId}/instruction-preview`), [paymentId]);
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

  useChatScope({ paymentId, quoteId: data?.quote_id });
  useEffect(() => {
    loadHealth()
      .then((h) => setSandbox({ code: h.demo?.mfa_code ?? "", on: h.mode === "sandbox" }))
      .catch(() => undefined);
  }, []);

  const blockers = data?.readiness.blockers ?? [];
  const codes = new Set(blockers.map((b) => b.code));
  const live =
    data !== null &&
    (data.state === "APPROVED" || data.state === "SUBMITTED" || codes.has("KYC_NOT_VERIFIED") || codes.has("QUOTE_EXPIRED"));
  const refreshAll = () => {
    payment.reload();
    tracker.reload();
    preview.reload();
  };
  usePolling(() => { payment.reload(); tracker.reload(); }, 2500, live);

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
  if (payment.loading && !data) return <Loading what="Loading the payment" />;
  if (!data) {
    return (
      <div className="stack">
        <ErrorNotice error={payment.error} />
        <Link to="/payments">Back to payments</Link>
      </div>
    );
  }

  const perms = user.permissions;
  const can = (permission: string) => perms.includes(permission);
  const state = data.state;
  const base = `/payments/${data.payment_id}`;

  const requestApproval = () =>
    run("request", () => post<ApprovalRequested>(`${base}/request-approval`, {}, { idempotencyKey: requestKey }));
  const reject = () => run("reject", () => post(`${base}/reject`, { reason: "Rejected at the approval stage" }, { idempotencyKey: rejectKey }));
  const cancel = () => run("cancel", () => post(`${base}/cancel`, {}, { idempotencyKey: cancelKey }));
  const approveWith = (proof: string) => {
    setMfaOpen(false);
    const hash = data.summary_hash ?? "";
    void run("approve", async () => {
      await post(`${base}/approve`, { confirm_summary_hash: hash }, { idempotencyKey: approveKey, mfaProof: proof });
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
      await post(`${base}/requote`, { quote_id: fresh.quote_id, provider_id: data.provider_id }, { idempotencyKey: requoteKey });
    });

  const terminal = ["SETTLED", "REJECTED", "CANCELLED", "FAILED"].includes(state);
  const open = ["DRAFT", "QUOTED", "PENDING_APPROVAL"].includes(state);
  return (
    <div className="stack">
      <PageHead title={`Payment to ${data.recipient.label}`} actions={<StateBadge state={state} />}>
        {data.target.formatted} for {data.purpose.toLowerCase()} via {data.provider_name}. Simulated: no real money moves.
      </PageHead>
      <ErrorNotice error={error} />

      {state === "DRAFT" ? (
        <Notice tone="warn" title="This payment needs a fresh quote">
          The earlier quote expired, so the payment went back to draft. Get a new quote from the same provider to continue.
        </Notice>
      ) : null}
      {data.failure_reason ? <Notice tone="danger" title="The payment did not complete">{data.failure_reason}</Notice> : null}
      {state === "SETTLED" ? <Notice tone="ok" title="Settled (simulated)">The simulated provider credited the beneficiary.</Notice> : null}

      <SummaryCard payment={data} />

      {blockers.length > 0 ? (
        <section className="card" aria-labelledby="blockers-title">
          <h2 id="blockers-title">Before this can be approved</h2>
          <ul>
            {blockers.map((b) => (
              <li key={b.code}>
                <strong>{b.message}</strong>
                {b.code === "RECIPIENT_NOT_ALLOWLISTED" ? <> <Link to="/recipients">Open recipients</Link>.</> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {open && user.role !== "admin" ? <KycCard /> : null}

      <section className="card" aria-labelledby="actions-title">
        <h2 id="actions-title">Actions</h2>
        <div className="row">
          {state === "DRAFT" && can("payments:draft") ? (
            <button type="button" className="btn primary" disabled={busy !== null} onClick={() => void requote()}>
              Get a fresh quote
            </button>
          ) : null}
          {state === "QUOTED" && can("payments:request_approval") ? (
            <button type="button" className="btn primary" disabled={busy !== null || !data.readiness.can_request_approval} onClick={() => void requestApproval()}>
              Request approval
            </button>
          ) : null}
          {state === "PENDING_APPROVAL" && can("payments:approve") ? (
            <button type="button" className="btn primary" disabled={busy !== null || !data.readiness.can_approve} onClick={() => setMfaOpen(true)}>
              Approve with MFA
            </button>
          ) : null}
          {state === "PENDING_APPROVAL" && can("payments:reject") ? (
            <button type="button" className="btn danger" disabled={busy !== null} onClick={() => void reject()}>Reject</button>
          ) : null}
          {["DRAFT", "QUOTED", "PENDING_APPROVAL", "APPROVED"].includes(state) && can("payments:cancel") ? (
            <button type="button" className="btn" disabled={busy !== null} onClick={() => void cancel()}>Cancel payment</button>
          ) : null}
          <Link className="btn" to={`/audit?payment_id=${data.payment_id}`}>See its audit trail</Link>
          {can("audit:read") ? <Link className="btn" to={`${base}/report`}>Compliance report</Link> : null}
        </div>
        {terminal ? <p className="small muted">This payment is finished and cannot change.</p> : null}
        {!terminal && !can("payments:approve") && user.role !== "admin" ? (
          <p className="small muted">Only the paying parent can request approval and approve. Approval always needs a fresh MFA code.</p>
        ) : null}
        {state === "PENDING_APPROVAL" && !data.readiness.can_approve && blockers.length > 0 ? (
          <p className="small muted">Approval is disabled until the items above are resolved.</p>
        ) : null}
        <p className="small muted">The assistant can suggest these steps but can never take them. {data.disclaimer}</p>
      </section>

      <div className="grid two weighted">
        {preview.data ? <Mt103Card preview={preview.data} /> : <Loading what="Preparing the instruction preview" />}
        {tracker.data ? <TrackerCard tracker={tracker.data} /> : <Loading what="Loading the tracker" />}
      </div>

      {sandbox.on && can("payments:approve") ? <SecurityDemo payment={data} attempt={attempt} /> : null}

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
