import { useState } from "react";

import { get, post, put } from "../api/client";
import type { KycView } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useAsync, usePolling } from "../hooks";
import { ErrorNotice, KycBadge, Loading, Notice } from "./Ui";

/** F5 mock KYC gate. Approval stays blocked until the status is VERIFIED. */
export function KycCard({ payerId }: { payerId?: string }) {
  const { user, reloadUser } = useAuth();
  const needsPayer = user?.role === "admin";
  const kyc = useAsync(
    () => {
      if (needsPayer && !payerId) return Promise.resolve(null);
      const query = needsPayer && payerId ? `?user_id=${encodeURIComponent(payerId)}` : "";
      return get<KycView>(`/kyc/status${query}`);
    },
    [needsPayer, payerId],
  );
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const data = kyc.data;
  usePolling(kyc.reload, 2000, data?.status === "PENDING");

  async function submitDocuments() {
    if (!data) return;
    setBusy(true);
    setError(null);
    try {
      await post("/kyc/mock-submit", { documents: data.required_documents.map((d) => d.key) });
      kyc.reload();
      await reloadUser();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  async function review(status: string) {
    setError(null);
    try {
      await put("/kyc/mock-review", { user_id: payerId, status });
      kyc.reload();
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <section className="card" aria-labelledby="kyc-title">
      <h2 id="kyc-title">Identity check (simulated)</h2>
      <ErrorNotice error={error ?? kyc.error} />
      {needsPayer && !payerId ? <p className="muted">Enter a payer user id to review their simulated KYC.</p> : null}
      {kyc.loading && !data && (!needsPayer || payerId) ? <Loading what="Checking" /> : null}
      {data ? (
        <>
          <p><KycBadge status={data.status} /></p>
          <p>{data.message}</p>
          {data.status === "NEEDS_DOCUMENTS" ? (
            <>
              <p className="small">Mock documents the sandbox asks for: {data.required_documents.map((d) => d.label).join(", ")}.</p>
              <button type="button" className="btn primary" disabled={busy} onClick={submitDocuments}>Submit mock documents</button>
            </>
          ) : null}
          {data.status === "PENDING" ? <p className="small muted">The simulated review takes a few seconds. This page updates by itself.</p> : null}
          {data.status !== "VERIFIED" ? <Notice tone="info">Approval is blocked until this is verified. No real identity data is used.</Notice> : null}
        </>
      ) : null}
      {user?.role === "admin" && payerId ? (
        <div className="row">
          <span className="small muted">Sandbox reviewer override:</span>
          {["VERIFIED", "PENDING", "NEEDS_DOCUMENTS"].map((s) => (
            <button key={s} type="button" className="btn small" onClick={() => void review(s)}>{s}</button>
          ))}
        </div>
      ) : null}
    </section>
  );
}
