import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { get, post } from "../api/client";
import type { ChainAnchor, ChainStatus, CorridorList, EscrowView, Health, Recipient } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { AnchorCard, ChainCard, EscrowCard, TimeControl } from "../components/EscrowPanels";
import { KycCard } from "../components/KycCard";
import { ErrorNotice, Field, Loading, Notice, PageHead } from "../components/Ui";
import { useAsync, usePolling } from "../hooks";
import { useIdempotencyKey } from "../idempotency";
import { formDefaults } from "../lib/corridors";
import { addDaysIso } from "../lib/format";
import { parseMajorToMinor } from "../lib/money";

type Purpose = "TUITION" | "LIVING";

interface PlanFormProps {
  recipients: Recipient[];
  corridors: CorridorList;
  onPlanned: () => void;
}

/** Plan an escrow: pick who gets paid, how much, and when. Nothing is locked until MFA confirms it. */
function PlanForm({ recipients, corridors, onPlanned }: PlanFormProps) {
  const [recipientId, setRecipientId] = useState(recipients[0]?.recipient_id ?? "");
  const [purpose, setPurpose] = useState<Purpose>("TUITION");
  const [tranches, setTranches] = useState("1");
  const [amount, setAmount] = useState("");
  const [first, setFirst] = useState(() => addDaysIso(14));
  const [reference, setReference] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const recipient = recipients.find((r) => r.recipient_id === recipientId);
  const corridor = corridors.items.find((c) => c.country === recipient?.country);
  const key = useIdempotencyKey(`${recipientId}|${purpose}|${tranches}|${amount}|${first}|${reference}`);

  /** Starting amount for the chosen currency: one tuition payment, or a month of living costs each. */
  function suggest(nextPurpose: Purpose, count: number, nextRecipient: Recipient | undefined) {
    const target = corridors.items.find((c) => c.country === nextRecipient?.country);
    if (!target) return;
    const defaults = formDefaults(target);
    setAmount(nextPurpose === "TUITION" ? defaults.amount : String(Number(defaults.sendPlanMonthly) * count));
  }

  function chooseRecipient(id: string) {
    setRecipientId(id);
    suggest(purpose, Number(tranches) || 1, recipients.find((r) => r.recipient_id === id));
  }

  function choosePurpose(next: Purpose) {
    const count = next === "LIVING" ? 3 : 1;
    setPurpose(next);
    setTranches(String(count));
    suggest(next, count, recipient);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFormError(null);
    if (!recipient || !corridor) return setFormError("Choose who gets paid.");
    const parsed = parseMajorToMinor(amount, corridor.exponent);
    if (!parsed.ok) return setFormError(parsed.error);
    const count = Number(tranches);
    if (!Number.isInteger(count) || count < 1 || count > 24) return setFormError("Use 1 to 24 tranches.");
    setBusy(true);
    try {
      await post("/escrows", {
        recipient_id: recipient.recipient_id,
        purpose,
        total: { amount_minor: parsed.minor, currency: corridor.currency },
        tranches: count,
        first_release: first,
        cadence: count > 1 ? "MONTHLY" : "ONCE",
        reference: reference.trim(),
      }, { idempotencyKey: key });
      setReference("");
      onPlanned();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card accent" onSubmit={submit} aria-labelledby="escrow-plan-title">
      <h2 id="escrow-plan-title">Plan an escrow</h2>
      <p className="muted">
        Lock money in a smart contract that pays on the dates you choose. Planning locks nothing: you
        see the schedule first, then confirm with MFA. Tuition is one payment on the due date; living
        costs are a payment every month.
      </p>
      <ErrorNotice error={error} />
      <div className="form-grid">
        <Field label="Who gets paid" htmlFor="escrow-recipient">
          <select id="escrow-recipient" value={recipientId} onChange={(e) => chooseRecipient(e.target.value)} required>
            {recipients.map((r) => <option key={r.recipient_id} value={r.recipient_id}>{r.label}</option>)}
          </select>
        </Field>
        <Field label="What for" htmlFor="escrow-purpose">
          <select id="escrow-purpose" value={purpose} onChange={(e) => choosePurpose(e.target.value as Purpose)}>
            <option value="TUITION">Tuition (one payment)</option>
            <option value="LIVING">Living costs (monthly)</option>
          </select>
        </Field>
        <Field label={`Total to lock${corridor ? ` (${corridor.currency})` : ""}`} htmlFor="escrow-amount" error={formError}>
          <input id="escrow-amount" value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required />
        </Field>
        <Field label="Number of payments" htmlFor="escrow-tranches" hint="1 to 24. Several means one a month.">
          <input id="escrow-tranches" value={tranches} onChange={(e) => setTranches(e.target.value)} inputMode="numeric" />
        </Field>
        <Field label={Number(tranches) > 1 ? "First payment on" : "Pay on"} htmlFor="escrow-first">
          <input id="escrow-first" type="date" value={first} onChange={(e) => setFirst(e.target.value)} required />
        </Field>
        <Field label="Reference" htmlFor="escrow-reference" hint="For example the invoice number. Only a hash of it goes on the chain.">
          <input id="escrow-reference" value={reference} onChange={(e) => setReference(e.target.value)} maxLength={70} required placeholder="INV-2026-4471 / STU-883201" />
        </Field>
      </div>
      <button type="submit" className="btn primary" disabled={busy || !recipient || !amount.trim() || !reference.trim()}>
        Plan escrow
      </button>
    </form>
  );
}

export function EscrowScreen() {
  const { user } = useAuth();
  const can = (permission: string) => user?.permissions.includes(permission) ?? false;
  const canWrite = can("escrow:write");
  const escrows = useAsync(() => get<{ items: EscrowView[] }>("/escrows"), []);
  const chain = useAsync(() => get<ChainStatus>("/chain/status"), []);
  const anchors = useAsync(() => get<{ items: ChainAnchor[] }>("/chain/anchors"), []);
  const recipients = useAsync(() => (canWrite ? get<{ items: Recipient[] }>("/recipients") : Promise.resolve({ items: [] })), [canWrite]);
  const corridors = useAsync(() => get<CorridorList>("/corridors"), []);
  const health = useAsync(() => get<Health>("/health", { auth: false }), []);

  const items = escrows.data?.items ?? [];
  // Keep refreshing while something can change by itself: a schedule paying out, or a plan waiting
  // for KYC to be verified.
  const live = items.some(
    (e) =>
      e.chain_status === "ACTIVE" ||
      e.chain_status === "FROZEN" ||
      (e.status === "PENDING_CONFIRMATION" && (e.blockers?.length ?? 0) > 0),
  );
  const refresh = () => {
    escrows.reload();
    chain.reload();
    anchors.reload();
  };
  usePolling(refresh, 3000, live);

  const people = recipients.data?.items ?? [];

  return (
    <div className="stack">
      <PageHead title="Smart escrow">
        Tuition and living costs locked in a smart contract that pays on the dates you choose, with a bank-style safety net.
      </PageHead>
      <Notice tone="info" title="A simulated chain">
        The contracts are real Solidity, run on an in-memory EVM inside the sandbox: no network, no
        real tokens, nothing is money. The parent decides (with MFA), the contract enforces, the
        bank&apos;s reviewer can freeze but never move funds, and the AI has no access at all. Only amounts,
        dates and hashes go on the chain.
      </Notice>
      <ErrorNotice error={escrows.error ?? chain.error ?? anchors.error} />
      {user?.role === "parent" && user.kyc_status !== "VERIFIED" ? <KycCard /> : null}
      {canWrite && recipients.data && corridors.data ? (
        people.length > 0 ? (
          <PlanForm recipients={people} corridors={corridors.data} onPlanned={refresh} />
        ) : (
          <Notice tone="warn" title="Add a recipient first">
            An escrow pays someone. <Link to="/recipients">Add the university or the student</Link>, then plan an escrow.
          </Notice>
        )
      ) : null}
      <section className="stack" aria-labelledby="escrows-title">
        <h2 id="escrows-title">Escrows</h2>
        {escrows.loading && !escrows.data ? <Loading what="Loading escrows" /> : null}
        {escrows.data && items.length === 0 ? <p className="muted">No escrows yet.</p> : null}
        {items.map((escrow) => (
          <EscrowCard
            key={escrow.escrow_id}
            escrow={escrow}
            canWrite={canWrite}
            canFreeze={can("escrow:freeze")}
            canControl={can("sandbox:control")}
            sandboxCode={health.data?.demo?.mfa_code}
            onChanged={refresh}
          />
        ))}
      </section>
      <AnchorCard
        anchors={anchors.data?.items ?? []}
        canAnchor={can("chain:anchor")}
        canVerify={can("audit:verify")}
        onChanged={refresh}
      />
      {can("sandbox:control") ? <TimeControl onChanged={refresh} /> : null}
      {chain.data ? <ChainCard status={chain.data} /> : null}
    </div>
  );
}
