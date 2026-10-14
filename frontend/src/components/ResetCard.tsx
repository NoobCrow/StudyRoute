import { useState } from "react";

import { post } from "../api/client";
import { ErrorNotice, Notice } from "./Ui";

interface ResetResult { reset: boolean; deleted: Record<string, number> }

/** "Reset my data" (blueprint 12.4). Two steps, because it cannot be undone. */
export function ResetCard({ onDone }: { onDone: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<ResetResult | null>(null);

  async function reset() {
    setBusy(true);
    setError(null);
    try {
      setResult(await post<ResetResult>("/me/reset"));
      setConfirming(false);
      onDone();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="reset-title">
      <h2 id="reset-title">Your data</h2>
      <p className="muted">
        This is a sandbox with synthetic data. You can delete your payments, quotes, recipients and
        documents at any time. The audit log keeps its entries, which hold no personal details.
      </p>
      <ErrorNotice error={error} />
      {result ? (
        <Notice tone="ok" title="Your data was deleted">
          {Object.entries(result.deleted).map(([name, count]) => `${count} ${name}`).join(", ")}.
          Add a recipient again before creating a new payment.
        </Notice>
      ) : null}
      {confirming ? (
        <div className="row">
          <strong>Delete all of it? This cannot be undone.</strong>
          <button type="button" className="btn danger" disabled={busy} onClick={() => void reset()}>
            Yes, delete my data
          </button>
          <button type="button" className="btn" onClick={() => setConfirming(false)}>Keep it</button>
        </div>
      ) : (
        <button type="button" className="btn" onClick={() => setConfirming(true)}>Reset my data</button>
      )}
    </section>
  );
}
