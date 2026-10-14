import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { get, patch, post } from "../api/client";
import type { Corridor, CorridorList, Recipient } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { MfaDialog } from "../components/MfaDialog";
import { CountryOptions } from "../components/CountryOptions";
import { Badge, ErrorNotice, Field, Loading, Notice, PageHead } from "../components/Ui";
import { loadHealth } from "../health";
import { useAsync } from "../hooks";
import { formatDateTime } from "../lib/format";

const BIC_PATTERN = /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/;
const EXAMPLE = { bic: "EXMPGB2L", iban: "GB08EXMP12345612344821", name: "University of Example (synthetic)" };

type UkMode = "iban" | "domestic";

interface FormState {
  type: "UNIVERSITY" | "STUDENT";
  name: string;
  country: string;
  bic: string;
  iban: string;
  account: string;
  routing: string;
  ukMode: UkMode;
}

const EMPTY: FormState = { type: "UNIVERSITY", name: "", country: "GB", bic: "", iban: "", account: "", routing: "", ukMode: "iban" };

function usesIban(corridor: Corridor | undefined, ukMode: UkMode): boolean {
  if (!corridor) return true;
  return corridor.account_scheme === "IBAN" || (corridor.account_scheme === "IBAN_OR_UK_DOMESTIC" && ukMode === "iban");
}

function localProblem(form: FormState, corridor: Corridor | undefined): string | null {
  if (form.name.trim().length < 2) return "Enter the recipient's name.";
  if (!BIC_PATTERN.test(form.bic.trim().toUpperCase())) return "A BIC has 8 or 11 letters and digits, for example EXMPGB2L.";
  if (usesIban(corridor, form.ukMode) && !form.iban.trim()) return "Enter the IBAN.";
  if (!usesIban(corridor, form.ukMode) && !form.account.trim()) return "Enter the account number.";
  return null;
}

function buildBody(form: FormState, corridor: Corridor | undefined): Record<string, string> {
  const body: Record<string, string> = {
    type: form.type,
    display_name: form.name.trim(),
    country: form.country,
    bic: form.bic.trim().toUpperCase(),
  };
  if (usesIban(corridor, form.ukMode)) body.iban = form.iban.trim();
  else {
    body.account_number = form.account.trim();
    if (form.routing.trim()) body.routing_code = form.routing.trim();
  }
  return body;
}

function RecipientForm({ corridors, onCreated }: { corridors: Corridor[]; onCreated: () => void }) {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<Error | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const corridor = corridors.find((c) => c.country === form.country);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));
  const scheme = corridor?.account_scheme;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = localProblem(form, corridor);
    setProblem(found);
    if (found) return;
    setBusy(true);
    setError(null);
    try {
      await post("/recipients", buildBody(form, corridor));
      setForm({ ...EMPTY, country: form.country });
      onCreated();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit} aria-labelledby="new-recipient-title">
      <h2 id="new-recipient-title">Add a recipient</h2>
      <p className="muted">Use synthetic details only. Never enter a real account number in the sandbox.</p>
      <ErrorNotice error={error} />
      {problem ? <p className="error-text" role="alert">{problem}</p> : null}
      <div className="form-grid">
        <Field label="Type" htmlFor="r-type">
          <select id="r-type" value={form.type} onChange={(e) => set("type", e.target.value as FormState["type"])}>
            <option value="UNIVERSITY">University</option>
            <option value="STUDENT">Student</option>
          </select>
        </Field>
        <Field label="Name" htmlFor="r-name">
          <input id="r-name" value={form.name} onChange={(e) => set("name", e.target.value)} maxLength={120} />
        </Field>
        <Field label="Country" htmlFor="r-country">
          <select id="r-country" value={form.country} onChange={(e) => set("country", e.target.value)}>
            <CountryOptions corridors={corridors} />
          </select>
        </Field>
        <Field label="Bank BIC (SWIFT code)" htmlFor="r-bic" hint="8 or 11 characters. The country letters must match.">
          <input id="r-bic" value={form.bic} onChange={(e) => set("bic", e.target.value.toUpperCase())} maxLength={11} autoCapitalize="characters" />
        </Field>
      </div>
      {scheme === "IBAN_OR_UK_DOMESTIC" ? (
        <fieldset>
          <legend>Account format</legend>
          <div className="radio-row">
            <label><input type="radio" name="uk-mode" checked={form.ukMode === "iban"} onChange={() => set("ukMode", "iban")} /> IBAN</label>
            <label><input type="radio" name="uk-mode" checked={form.ukMode === "domestic"} onChange={() => set("ukMode", "domestic")} /> UK sort code and account</label>
          </div>
        </fieldset>
      ) : null}
      <div className="form-grid">
        {usesIban(corridor, form.ukMode) ? (
          <Field label="IBAN" htmlFor="r-iban" hint="The check digits are verified (ISO 13616, mod 97).">
            <input id="r-iban" value={form.iban} onChange={(e) => set("iban", e.target.value)} autoComplete="off" />
          </Field>
        ) : (
          <>
            <Field label="Account number" htmlFor="r-account" hint={scheme === "IBAN_OR_UK_DOMESTIC" ? "8 digits." : undefined}>
              <input id="r-account" value={form.account} onChange={(e) => set("account", e.target.value)} autoComplete="off" />
            </Field>
            {scheme === "IBAN_OR_UK_DOMESTIC" || scheme === "ABA_ACCOUNT" ? (
              <Field
                label={scheme === "ABA_ACCOUNT" ? "ABA routing number" : "Sort code"}
                htmlFor="r-routing"
                hint={scheme === "ABA_ACCOUNT" ? "9 digits with a checksum." : "6 digits."}
              >
                <input id="r-routing" value={form.routing} onChange={(e) => set("routing", e.target.value)} autoComplete="off" />
              </Field>
            ) : null}
          </>
        )}
      </div>
      <div className="row">
        <button type="submit" className="btn primary" disabled={busy}>Save recipient</button>
        {form.country === "GB" ? (
          <button
            type="button"
            className="btn ghost small"
            onClick={() => setForm({ ...EMPTY, name: EXAMPLE.name, bic: EXAMPLE.bic, iban: EXAMPLE.iban })}
          >
            Fill a synthetic example
          </button>
        ) : null}
      </div>
    </form>
  );
}

export function RecipientsScreen() {
  const { user } = useAuth();
  const corridors = useAsync(() => get<CorridorList>("/corridors"), []);
  const recipients = useAsync(() => get<{ items: Recipient[] }>("/recipients"), []);
  const [mfaFor, setMfaFor] = useState<{ recipient: Recipient; allowlist: boolean } | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [mfaCode, setMfaCode] = useState("");

  useEffect(() => {
    loadHealth().then((h) => setMfaCode(h.demo?.mfa_code ?? "")).catch(() => undefined);
  }, []);

  async function applyAllowlist(proof: string) {
    if (!mfaFor) return;
    const { recipient, allowlist } = mfaFor;
    setMfaFor(null);
    setError(null);
    try {
      await patch(`/recipients/${recipient.recipient_id}`, { allowlisted: allowlist }, { mfaProof: proof });
      recipients.reload();
    } catch (e) {
      setError(e as Error);
    }
  }

  if (!user) return null;
  const canAllowlist = user.permissions.includes("recipients:allowlist");
  const items = recipients.data?.items ?? [];

  return (
    <div className="stack">
      <PageHead title="Recipients">
        Universities and students you can pay. A recipient must be allowlisted, with a fresh MFA code, before a payment to it can be approved.
      </PageHead>
      <ErrorNotice error={recipients.error ?? error} />
      {recipients.loading && !recipients.data ? <Loading /> : null}
      {items.length > 0 ? (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Recipients table">
          <table>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Country</th>
                <th scope="col">BIC</th>
                <th scope="col">Account (masked)</th>
                <th scope="col">Allowlist</th>
                <th scope="col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.recipient_id}>
                  <td>
                    {/* Rendered as plain text: the UI never injects recipient names as HTML. */}
                    <strong>{r.display_name}</strong>
                    <div className="small muted">{r.type === "UNIVERSITY" ? "University" : "Student"} - added {formatDateTime(r.created_at)}</div>
                  </td>
                  <td>{r.country}</td>
                  <td className="mono">{r.bic}</td>
                  <td className="mono">{r.account_masked}{r.routing_code ? <div className="small muted">routing {r.routing_code}</div> : null}</td>
                  <td>{r.allowlisted ? <Badge tone="ok">Allowlisted</Badge> : <Badge tone="warn">Not allowlisted</Badge>}</td>
                  <td>
                    {canAllowlist ? (
                      <button type="button" className="btn small" onClick={() => setMfaFor({ recipient: r, allowlist: !r.allowlisted })}>
                        {r.allowlisted ? "Remove from allowlist" : "Allowlist with MFA"}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {recipients.data && items.length === 0 ? <Notice tone="info">No recipients yet. Add the university below.</Notice> : null}
      {!canAllowlist ? <p className="small muted">Only the paying parent can allowlist a recipient.</p> : null}
      {corridors.data ? <RecipientForm corridors={corridors.data.items} onCreated={recipients.reload} /> : <Loading />}
      {mfaFor ? (
        <MfaDialog
          title={mfaFor.allowlist ? "Allowlist this recipient" : "Remove from the allowlist"}
          scope="allowlist_recipient"
          subjectId={mfaFor.recipient.recipient_id}
          sandboxCode={mfaCode || undefined}
          onProof={(proof) => void applyAllowlist(proof)}
          onCancel={() => setMfaFor(null)}
        />
      ) : null}
    </div>
  );
}
