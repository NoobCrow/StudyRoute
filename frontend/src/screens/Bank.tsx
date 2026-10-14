import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { get, post } from "../api/client";
import type {
  BankAccountView, BankNetwork, BankTransfer, Beneficiary, ChargeCode, Health,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { BankStatusBadge, NetworkCard, TransferDetail, isOpen } from "../components/BankPanels";
import { ErrorNotice, Field, Loading, Notice, PageHead } from "../components/Ui";
import { useAsync, usePolling } from "../hooks";
import { useIdempotencyKey } from "../idempotency";
import { parseMajorToMinor } from "../lib/money";

const CHARGE_LABEL: Record<ChargeCode, string> = {
  OUR: "OUR: I pay every fee",
  SHA: "SHA: fees are shared",
  BEN: "BEN: the beneficiary pays",
};

/** Which destinations make sense for a source: same country at home, or abroad from Bangladesh. */
function routeFits(source: BankAccountView, dest: Beneficiary): boolean {
  if (dest.id === source.id) return false;
  if (source.currency === "BDT") return true;
  return dest.currency === source.currency && dest.country === source.country;
}

interface PlanFormProps {
  accounts: BankAccountView[];
  beneficiaries: Beneficiary[];
  network: BankNetwork;
  onPlanned: (transfer: BankTransfer) => void;
}

function PlanForm({ accounts, beneficiaries, network, onPlanned }: PlanFormProps) {
  const [sourceId, setSourceId] = useState(accounts[0]?.id ?? "");
  const [destId, setDestId] = useState("");
  const [amount, setAmount] = useState("");
  const [rail, setRail] = useState("");
  const [charge, setCharge] = useState<ChargeCode | "">("");
  const [reference, setReference] = useState("Sandbox transfer");
  const [error, setError] = useState<Error | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const source = accounts.find((a) => a.id === sourceId);
  const choices = useMemo(
    () => (source ? beneficiaries.filter((b) => routeFits(source, b)) : []),
    [source, beneficiaries],
  );
  const dest = choices.find((b) => b.id === destId);
  const international = source?.currency === "BDT" && dest !== undefined && dest.currency !== "BDT";
  const sameBank = source !== undefined && dest !== undefined && source.bank_code === dest.bank_code;
  const rails = source ? (network.directory?.rails[source.currency] ?? []) : [];
  const key = useIdempotencyKey(`${sourceId}|${destId}|${amount}|${rail}|${charge}|${reference}`);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFormError(null);
    if (!source || !dest) return;
    const parsed = parseMajorToMinor(amount);
    if (!parsed.ok) {
      setFormError(parsed.error);
      return;
    }
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        source: source.id,
        destination: dest.id,
        amount: { amount_minor: parsed.minor, currency: dest.currency },
        reference: reference.trim() || "Sandbox transfer",
      };
      if (international && charge) body.charge_code = charge;
      if (!international && !sameBank && rail) body.rail = rail;
      onPlanned(await post<BankTransfer>("/bank/transfers", body, { idempotencyKey: key }));
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card accent" onSubmit={submit} aria-labelledby="plan-title">
      <h2 id="plan-title">Plan a transfer</h2>
      <p className="muted">
        Planning moves no money. You will see the fees and every hop first, then confirm with MFA.
        Pick a Bangladesh account and a UK account to see an international transfer, or two Bangladesh
        accounts to see a national one.
      </p>
      <ErrorNotice error={error} />
      <div className="form-grid">
        <Field label="From account" htmlFor="bank-source">
          <select id="bank-source" value={sourceId} onChange={(e) => { setSourceId(e.target.value); setDestId(""); }} required>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.label} · {a.bank_name} · {a.balance.formatted}</option>
            ))}
          </select>
        </Field>
        <Field label="To account" htmlFor="bank-dest">
          <select id="bank-dest" value={destId} onChange={(e) => setDestId(e.target.value)} required>
            <option value="" disabled>Choose who gets the money</option>
            {choices.map((b) => (
              <option key={b.id} value={b.id}>{b.holder} · {b.bank_name} · {b.currency}</option>
            ))}
          </select>
        </Field>
        <Field
          label={dest ? `Amount the beneficiary receives (${dest.currency})` : "Amount"}
          htmlFor="bank-amount"
          error={formError}
          hint={international ? "Fees are added to what you pay with OUR, or taken from the amount with SHA and BEN." : undefined}
        >
          <input id="bank-amount" value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" placeholder="1000.00" required />
        </Field>
        {international ? (
          <Field label="Who pays the fees" htmlFor="bank-charge" hint="Check the university's payment instructions. Indicative. Confirm with your AD bank.">
            <select id="bank-charge" value={charge} onChange={(e) => setCharge(e.target.value as ChargeCode | "")}>
              <option value="">Bank default</option>
              {(Object.keys(CHARGE_LABEL) as ChargeCode[]).map((code) => (
                <option key={code} value={code}>{CHARGE_LABEL[code]}</option>
              ))}
            </select>
          </Field>
        ) : dest && !sameBank ? (
          <Field label="Way of sending" htmlFor="bank-rail">
            <select id="bank-rail" value={rail} onChange={(e) => setRail(e.target.value)}>
              <option value="">Cheapest that accepts the amount</option>
              {rails.map((r) => <option key={r.code} value={r.code}>{r.label}</option>)}
            </select>
          </Field>
        ) : null}
        <Field label="Reference" htmlFor="bank-reference">
          <input id="bank-reference" value={reference} onChange={(e) => setReference(e.target.value)} maxLength={140} />
        </Field>
      </div>
      <button type="submit" className="btn primary" disabled={busy || !source || !dest || !amount.trim()}>
        Plan transfer
      </button>
    </form>
  );
}

function AccountsTable({ accounts }: { accounts: BankAccountView[] }) {
  return (
    <section className="card" aria-labelledby="accounts-title">
      <h2 id="accounts-title">Accounts</h2>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Bank accounts table">
        <table>
          <caption className="sr-only">Simulated bank accounts and balances</caption>
          <thead>
            <tr><th scope="col">Account</th><th scope="col">Bank</th><th scope="col" className="hide-narrow">Number</th><th scope="col" className="num">Balance</th></tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <tr key={a.id}>
                <td><strong>{a.label}</strong><div className="small muted">{a.holder}</div></td>
                <td>{a.bank_name}</td>
                <td className="hide-narrow"><code>{a.number}</code></td>
                <td className="num">{a.balance.formatted}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function BankScreen() {
  const { user } = useAuth();
  const canTransfer = user?.permissions.includes("bank:transfer") ?? false;
  const canControl = user?.permissions.includes("sandbox:control") ?? false;
  const network = useAsync(() => get<BankNetwork>("/bank/network"), []);
  const accounts = useAsync(() => get<{ items: BankAccountView[] }>("/bank/accounts"), []);
  const people = useAsync(() => get<{ items: Beneficiary[] }>("/bank/beneficiaries"), []);
  const transfers = useAsync(() => get<{ items: BankTransfer[] }>("/bank/transfers?limit=20"), []);
  const health = useAsync(() => get<Health>("/health", { auth: false }), []);
  const [openId, setOpenId] = useState<string | null>(null);
  const [active, setActive] = useState<BankTransfer | null>(null);

  const list = transfers.data?.items ?? [];
  const live = list.some((t) => isOpen(t.status)) || (active !== null && isOpen(active.status));
  const refresh = () => {
    network.reload();
    accounts.reload();
    transfers.reload();
    if (openId) void get<BankTransfer>(`/bank/transfers/${openId}`).then(setActive).catch(() => undefined);
  };
  usePolling(refresh, 2000, live);

  function open(transfer: BankTransfer) {
    setOpenId(transfer.id);
    void get<BankTransfer>(`/bank/transfers/${transfer.id}`).then(setActive);
  }

  const ready = network.data?.ready ?? false;
  const mine = accounts.data?.items ?? [];

  return (
    <div className="stack">
      <PageHead title="Bank network">
        Invented banks that pass simulated money to each other, inside Bangladesh and across borders. No real bank is contacted.
      </PageHead>
      <Notice tone="info" title="Everything here is simulated">
        The banks, accounts, fees and timings are made up for the sandbox. Try the names <code>FAIL_TEST</code>,
        <code> SLOW_TEST</code> and <code>SANCTION_TEST</code> as beneficiaries to see the edge cases.
        International transfers need KYC to be verified: <Link to="/payments">verify it on a payment page</Link>.
      </Notice>
      <ErrorNotice error={network.error ?? accounts.error ?? transfers.error} />
      {network.loading && !network.data ? <Loading what="Opening the bank network" /> : null}
      {network.data && !ready ? <NetworkCard network={network.data} /> : null}
      {ready ? (
        <>
          <AccountsTable accounts={mine} />
          {canTransfer && network.data && people.data && accounts.data ? (
            <PlanForm
              accounts={mine}
              beneficiaries={people.data.items}
              network={network.data}
              onPlanned={(transfer) => {
                setOpenId(transfer.id);
                setActive(transfer);
                transfers.reload();
              }}
            />
          ) : null}
          {active ? (
            <TransferDetail
              transfer={active}
              canTransfer={canTransfer}
              canControl={canControl}
              sandboxCode={health.data?.demo?.mfa_code}
              onChanged={refresh}
            />
          ) : null}
          <section className="card" aria-labelledby="transfers-title">
            <h2 id="transfers-title">Transfers</h2>
            {list.length === 0 ? <p className="muted">No transfers yet.</p> : (
              <div className="table-wrap" tabIndex={0} role="region" aria-label="Transfers table">
                <table>
                  <caption className="sr-only">Simulated transfers, newest first</caption>
                  <thead>
                    <tr><th scope="col">To</th><th scope="col" className="hide-narrow">Kind</th><th scope="col" className="num">You paid</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Open</span></th></tr>
                  </thead>
                  <tbody>
                    {list.map((t) => (
                      <tr key={t.id} className={t.id === openId ? "best" : undefined}>
                        <td>{t.destination.holder}<div className="small muted">{t.destination.bank_name}</div></td>
                        <td className="hide-narrow">{t.kind === "INTERNATIONAL" ? "International" : `National (${t.rail})`}</td>
                        <td className="num">{t.debit.formatted}</td>
                        <td><BankStatusBadge status={t.status} /></td>
                        <td>
                          <button type="button" className="btn small" onClick={() => open(t)} aria-label={`Open transfer to ${t.destination.holder}`}>
                            Open
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          {network.data ? <NetworkCard network={network.data} /> : null}
        </>
      ) : null}
    </div>
  );
}
