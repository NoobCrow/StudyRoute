import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { get, put } from "../api/client";
import type { RuleView } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge, ErrorNotice, Field, Loading, Notice, NotVerifiedBadge, PageHead } from "../components/Ui";
import { useAsync } from "../hooks";

interface RulesResponse { rules: RuleView[]; unverified_count: number; disclaimer: string }

function compact(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 70 ? `${text.slice(0, 67)}...` : text;
}

function EditDialog({ rule, onDone, onCancel }: { rule: RuleView; onDone: () => void; onCancel: () => void }) {
  const [value, setValue] = useState(() => JSON.stringify(rule.value, null, 2));
  const [source, setSource] = useState(rule.source_url ?? "");
  const [verified, setVerified] = useState(rule.verified);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === "Escape" && onCancel();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onCancel]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    let parsed: unknown;
    try {
      parsed = JSON.parse(value);
    } catch {
      return setProblem("The value must be valid JSON, for example 300, true or \"15:00\".");
    }
    if (verified && !source.trim()) return setProblem("A verified rule needs the source URL it was checked against.");
    setProblem(null);
    setBusy(true);
    try {
      await put("/config/rules", { key: rule.key, value: parsed, source_url: source.trim() || null, verified, reason: reason.trim() });
      onDone();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overlay">
      <form className="dialog wide" role="dialog" aria-modal="true" aria-labelledby="edit-title" onSubmit={submit}>
        <h2 id="edit-title">Change <code>{rule.key}</code></h2>
        <p className="muted">The change is written to the audit log with your name and the reason.</p>
        <ErrorNotice error={error} />
        {problem ? <p className="error-text" role="alert">{problem}</p> : null}
        <Field label="Value (JSON)" htmlFor="rule-value">
          <textarea id="rule-value" value={value} onChange={(e) => setValue(e.target.value)} spellCheck={false} />
        </Field>
        <Field label="Source URL" htmlFor="rule-source">
          <input id="rule-source" value={source} onChange={(e) => setSource(e.target.value)} />
        </Field>
        <label className="row">
          <input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} />
          Checked against the official source
        </label>
        <Field label="Why are you changing it?" htmlFor="rule-reason">
          <input id="rule-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={160} required />
        </Field>
        <div className="row">
          <button type="submit" className="btn primary" disabled={busy || reason.trim().length < 3}>Save change</button>
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </div>
  );
}

export function RulesScreen() {
  const { user } = useAuth();
  const rules = useAsync(() => get<RulesResponse>("/config/rules"), []);
  const [onlyUnverified, setOnlyUnverified] = useState(false);
  const [editing, setEditing] = useState<RuleView | null>(null);
  const canEdit = user?.permissions.includes("config:write") ?? false;
  const all = rules.data?.rules ?? [];
  const shown = onlyUnverified ? all.filter((r) => !r.verified) : all;

  return (
    <div className="stack">
      <PageHead title="Rules and limits">
        Every limit, fee assumption, calendar and checklist lives in configuration, never in code. Anything not checked against an official source is marked.
      </PageHead>
      {rules.data ? (
        <Notice tone={rules.data.unverified_count > 0 ? "warn" : "ok"} title={`${rules.data.unverified_count} rules are not verified`}>
          {rules.data.disclaimer}
        </Notice>
      ) : null}
      <ErrorNotice error={rules.error} />
      <label className="row">
        <input type="checkbox" checked={onlyUnverified} onChange={(e) => setOnlyUnverified(e.target.checked)} />
        Show only rules that are not verified
      </label>
      {rules.loading && !rules.data ? <Loading /> : null}
      {shown.length > 0 ? (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Rules table">
          <table>
            <thead>
              <tr>
                <th scope="col">Rule</th>
                <th scope="col">Value</th>
                <th scope="col">Status</th>
                <th scope="col">Source</th>
                {canEdit ? <th scope="col"><span className="sr-only">Edit</span></th> : null}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.key}>
                  <td><code>{r.key}</code><div className="small muted">{r.kind.replace("_", " ")}</div></td>
                  <td className="mono">{compact(r.value)}</td>
                  <td>
                    {r.verified ? <Badge tone="ok">Verified</Badge> : <NotVerifiedBadge />}
                    {r.indicative ? <div className="small">{r.indicative}</div> : null}
                  </td>
                  <td className="small">
                    {r.source_url ?? "-"}
                    {r.last_checked ? <div className="muted">checked {r.last_checked}</div> : null}
                    {r.note ? <div className="muted">{r.note}</div> : null}
                  </td>
                  {canEdit ? (
                    <td><button type="button" className="btn small" onClick={() => setEditing(r)}>Edit</button></td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {editing ? (
        <EditDialog
          rule={editing}
          onCancel={() => setEditing(null)}
          onDone={() => {
            setEditing(null);
            rules.reload();
          }}
        />
      ) : null}
    </div>
  );
}
