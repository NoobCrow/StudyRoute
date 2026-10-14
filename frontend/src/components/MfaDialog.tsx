import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { post } from "../api/client";
import { ErrorNotice } from "./Ui";

interface Props {
  title: string;
  scope: "approve_payment" | "allowlist_recipient" | "confirm_bank_transfer";
  subjectId: string;
  sandboxCode?: string;
  onProof: (proof: string) => void;
  onCancel: () => void;
}

/** Step-up MFA. The proof returned is bound to this user, this action and this subject. */
export function MfaDialog({ title, scope, subjectId, sandboxCode, onProof, onCancel }: Props) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    input.current?.focus();
    const close = (event: KeyboardEvent) => event.key === "Escape" && onCancel();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onCancel]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await post<{ mfa_proof: string }>("/auth/mfa/verify", { code: code.trim(), scope, subject_id: subjectId });
      onProof(result.mfa_proof);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overlay">
      <form className="dialog" role="dialog" aria-modal="true" aria-labelledby="mfa-title" onSubmit={submit}>
        <h2 id="mfa-title">{title}</h2>
        <p className="muted">
          Enter the 6-digit code from your authenticator app. The proof lasts 5 minutes and works once, for this action only.
        </p>
        {sandboxCode ? <p className="small">Sandbox hint: the demo code is <code>{sandboxCode}</code>.</p> : null}
        <ErrorNotice error={error} />
        <div className="field">
          <label htmlFor="mfa-code">MFA code</label>
          <input id="mfa-code" ref={input} value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={12} />
        </div>
        <div className="row">
          <button type="submit" className="btn primary" disabled={busy || code.trim().length < 4}>Verify</button>
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </div>
  );
}
