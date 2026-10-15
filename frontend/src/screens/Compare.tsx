import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { get, post } from "../api/client";
import type { ChargeCode, CorridorList, Payment, Quote, Recipient } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useChatScope } from "../chatContext";
import { Countdown } from "../components/Countdown";
import { QuoteTable } from "../components/QuoteTable";
import { StressCard } from "../components/StressCard";
import { CountryOptions } from "../components/CountryOptions";
import { ErrorNotice, Field, Loading, Notice, PageHead } from "../components/Ui";
import { useAsync } from "../hooks";
import { useIdempotencyKey } from "../idempotency";
import { addDaysIso } from "../lib/format";
import { formDefaults } from "../lib/corridors";
import { parseMajorToMinor } from "../lib/money";

const CHARGE_HELP: Record<ChargeCode, string> = {
  OUR: "You pay every fee. The university should receive the full invoice amount. Best for tuition.",
  SHA: "You pay your bank. Correspondent and receiving fees are taken from the amount, so the university may receive less.",
  BEN: "The beneficiary pays everything. This has the highest risk of a short payment.",
};

function ChargeAdvisor({ value }: { value: ChargeCode }) {
  return (
    <details className="small" open={value !== "OUR"}>
      <summary>Which charge code should I choose? (OUR, SHA, BEN)</summary>
      <ul>
        {(Object.keys(CHARGE_HELP) as ChargeCode[]).map((code) => (
          <li key={code}>
            <strong>{code}</strong>
            {code === "OUR" ? " (recommended for tuition)" : ""}: {CHARGE_HELP[code]}
          </li>
        ))}
      </ul>
      <p className="muted">Check the university's own payment instructions too. Indicative. Confirm with your AD bank.</p>
    </details>
  );
}

interface DraftProps {
  quote: Quote;
  providerId: string;
  recipients: Recipient[];
  initialRecipient: string;
}

function DraftForm({ quote, providerId, recipients, initialRecipient }: DraftProps) {
  const navigate = useNavigate();
  const matching = recipients.filter((r) => r.country === quote.destination_country);
  // Never guess who gets the money: preselect only when there is exactly one choice.
  const only = matching.length === 1 ? (matching[0]?.recipient_id ?? "") : "";
  const [recipientId, setRecipientId] = useState(initialRecipient || only);
  const [reference, setReference] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const key = useIdempotencyKey(`${quote.quote_id}|${providerId}|${recipientId}|${reference}`);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await post<Payment>(
        "/payments",
        {
          quote_id: quote.quote_id,
          provider_id: providerId,
          recipient_id: recipientId,
          reference: reference.trim(),
          due_date: quote.due_date,
        },
        { idempotencyKey: key },
      );
      navigate(`/payments/${created.payment_id}`);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card accent" onSubmit={submit} aria-labelledby="draft-title">
      <h2 id="draft-title">Create a draft payment</h2>
      <p className="muted">
        A draft changes nothing at the bank. You will review the approval summary and approve it yourself with MFA.
      </p>
      <ErrorNotice error={error} />
      {matching.length === 0 ? (
        <Notice tone="warn">
          You need a recipient in this country first. <Link to="/recipients">Add a recipient</Link>.
        </Notice>
      ) : null}
      <div className="form-grid">
        <Field label="Recipient" htmlFor="draft-recipient">
          <select id="draft-recipient" value={recipientId} onChange={(e) => setRecipientId(e.target.value)} required>
            <option value="" disabled>Choose a recipient</option>
            {matching.map((r) => (
              <option key={r.recipient_id} value={r.recipient_id}>
                {r.display_name} ({r.account_masked})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Payment reference" htmlFor="draft-reference" hint="Invoice number and student ID, so the university can match the payment.">
          <input
            id="draft-reference"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="INV-2026-4471 / STU-883201"
            maxLength={140}
            required
          />
        </Field>
      </div>
      <button type="submit" className="btn primary" disabled={busy || !recipientId || !reference.trim()}>
        Create draft with {quote.results.find((r) => r.provider_id === providerId)?.provider_name ?? providerId}
      </button>
    </form>
  );
}

export function CompareScreen() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const corridors = useAsync(() => get<CorridorList>("/corridors"), []);
  const recipients = useAsync(() => get<{ items: Recipient[] }>("/recipients"), []);
  const [country, setCountry] = useState("GB");
  const [purpose, setPurpose] = useState("TUITION");
  const [amount, setAmount] = useState("10000");
  const [charge, setCharge] = useState<ChargeCode>("OUR");
  const [recipientId, setRecipientId] = useState("");
  const [dueDate, setDueDate] = useState(() => addDaysIso(14));
  const [quote, setQuote] = useState<Quote | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const corridor = corridors.data?.items.find((c) => c.country === country);
  const countryRecipients = useMemo(
    () => (recipients.data?.items ?? []).filter((r) => r.country === country),
    [recipients.data, country],
  );
  useChatScope({ quoteId: quote?.quote_id });

  const sharedQuote = params.get("quote");
  const sharedProvider = params.get("provider");
  useEffect(() => {
    if (!sharedQuote) return;
    get<Quote>(`/quotes/${encodeURIComponent(sharedQuote)}`)
      .then((loaded) => {
        setQuote(loaded);
        setCountry(loaded.destination_country);
        setSelected(sharedProvider || loaded.deadline_fit?.best_in_time || loaded.results[0]?.provider_id || null);
      })
      .catch((e: unknown) => setError(e as Error));
  }, [sharedQuote, sharedProvider]);

  /** A new destination means a new currency, so the amount starts again from a sensible size for it. */
  function chooseCountry(next: string) {
    setCountry(next);
    setRecipientId("");
    const target = corridors.data?.items.find((c) => c.country === next);
    if (target) setAmount(formDefaults(target).amount);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!corridor) return setFormError("Choose a destination country.");
    const parsed = parseMajorToMinor(amount, corridor.exponent);
    if (!parsed.ok) return setFormError(parsed.error);
    setFormError(null);
    setBusy(true);
    try {
      const created = await post<Quote>("/quotes", {
        target: { amount_minor: parsed.minor, currency: corridor.currency },
        purpose,
        destination_country: country,
        charge_code: charge,
        recipient_id: recipientId || undefined,
        due_date: dueDate || undefined,
      });
      setQuote(created);
      setSelected(created.deadline_fit?.best_in_time ?? created.results[0]?.provider_id ?? null);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  const canDraft = user?.permissions.includes("payments:draft") ?? false;

  return (
    <div className="stack">
      <PageHead title="Compare providers">
        Rank providers by the true total cost, including the hidden exchange-rate margin and the fees taken on the way.
      </PageHead>
      <form className="card" onSubmit={submit} aria-labelledby="quote-title">
        <h2 id="quote-title">What should arrive?</h2>
        <div className="form-grid">
          <Field label="Destination" htmlFor="q-country">
            <select id="q-country" value={country} onChange={(e) => chooseCountry(e.target.value)}>
              <CountryOptions corridors={corridors.data?.items ?? []} withCurrency />
            </select>
          </Field>
          <Field label={`Amount the beneficiary must receive${corridor ? ` (${corridor.currency})` : ""}`} htmlFor="q-amount" error={formError}>
            <input id="q-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label="Purpose" htmlFor="q-purpose">
            <select id="q-purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)}>
              <option value="TUITION">Tuition</option>
              <option value="LIVING">Living costs</option>
            </select>
          </Field>
          <Field label="Charge code" htmlFor="q-charge">
            <select id="q-charge" value={charge} onChange={(e) => setCharge(e.target.value as ChargeCode)}>
              <option value="OUR">OUR (sender pays all)</option>
              <option value="SHA">SHA (shared)</option>
              <option value="BEN">BEN (beneficiary pays all)</option>
            </select>
          </Field>
          <Field label="University due date" htmlFor="q-due">
            <input id="q-due" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </Field>
          <Field label="Recipient (optional)" htmlFor="q-recipient">
            <select id="q-recipient" value={recipientId} onChange={(e) => setRecipientId(e.target.value)}>
              <option value="">Choose later</option>
              {countryRecipients.map((r) => (
                <option key={r.recipient_id} value={r.recipient_id}>{r.display_name}</option>
              ))}
            </select>
          </Field>
        </div>
        <ChargeAdvisor value={charge} />
        <ErrorNotice error={error} />
        <button type="submit" className="btn primary" disabled={busy || !corridor}>
          {busy ? "Asking providers..." : "Get quotes"}
        </button>
      </form>

      {busy && !quote ? <Loading what="Asking the synthetic providers" /> : null}
      {quote ? (
        <section className="card" aria-labelledby="results-title">
          <div className="row between">
            <h2 id="results-title">Results for {quote.target.formatted}</h2>
            <Countdown expiresAt={quote.expires_at} />
          </div>
          <p className="small muted">
            Mid-market rate {quote.mid_rate.display} ({quote.mid_rate.source}, as of {quote.mid_rate.as_of}). {quote.disclaimer}
          </p>
          <QuoteTable quote={quote} selected={selected} onSelect={setSelected} />
          <p className="small muted">Quote {quote.quote_id}. Input hash {quote.input_hash.slice(0, 18)}...</p>
        </section>
      ) : null}
      {quote ? <StressCard quoteId={quote.quote_id} providerId={selected ?? quote.results[0]?.provider_id ?? ""} /> : null}
      {quote && selected && canDraft ? (
        <DraftForm
          key={`${quote.quote_id}-${selected}`}
          quote={quote}
          providerId={selected}
          recipients={recipients.data?.items ?? []}
          initialRecipient={quote.recipient_id ?? recipientId}
        />
      ) : null}
      {quote && !canDraft ? (
        <Notice tone="info">Only the paying parent can create a draft payment. You can share this comparison and ask the assistant about it.</Notice>
      ) : null}
    </div>
  );
}
