"use client";

import { CircleCheck } from "lucide-react";
import { useState } from "react";

import { ErrorNotice, Notice } from "@/components/app/notice";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip, KycBadge } from "@/components/app/status";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { post, put } from "@/lib/api/client";
import type { KycView } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";

/** F5 mock KYC gate. Approval stays blocked until the status is VERIFIED. */
export function KycCard({ payerId }: { payerId?: string }) {
  const { user, reloadUser } = useAuth();
  const needsPayer = user?.role === "admin";
  const path = needsPayer
    ? payerId
      ? `/kyc/status?user_id=${encodeURIComponent(payerId)}`
      : null
    : "/kyc/status";
  const kyc = useApi<KycView>(path, {
    refetchInterval: (data) => ((data as KycView | undefined)?.status === "PENDING" ? 2000 : false),
  });
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const data = kyc.data;

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
    <Card aria-labelledby="kyc-title">
      <CardHeader>
        <CardTitle id="kyc-title" className="text-base">
          Identity check <span className="text-muted-foreground font-normal">(simulated)</span>
        </CardTitle>
        <CardAction>
          {data?.status === "VERIFIED" ? (
            <Chip tone="ok">
              <CircleCheck aria-hidden="true" />
              KYC verified (simulated)
            </Chip>
          ) : data ? (
            <KycBadge status={data.status} />
          ) : null}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorNotice error={error ?? kyc.error} onRetry={kyc.reload} />
        {needsPayer && !payerId ? (
          <p className="text-muted-foreground text-sm">
            Enter a payer user id to review their simulated KYC.
          </p>
        ) : null}
        {kyc.loading && !data && (!needsPayer || payerId) ? (
          <CardSkeleton lines={2} label="Checking" />
        ) : null}
        {data ? (
          <>
            <p>{data.message}</p>
            {data.status === "NEEDS_DOCUMENTS" ? (
              <>
                <p className="text-sm">
                  Mock documents the sandbox asks for:{" "}
                  {data.required_documents.map((d) => d.label).join(", ")}.
                </p>
                <Button type="button" loading={busy} onClick={() => void submitDocuments()}>
                  Submit mock documents
                </Button>
              </>
            ) : null}
            {data.status === "PENDING" ? (
              <p className="text-muted-foreground text-sm">
                The simulated review takes a few seconds. This page updates by itself.
              </p>
            ) : null}
            {data.status !== "VERIFIED" ? (
              <Notice tone="info">
                Approval is blocked until this is verified. No real identity data is used.
              </Notice>
            ) : null}
          </>
        ) : null}
        {user?.role === "admin" && payerId ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground text-sm">Sandbox reviewer override:</span>
            {["VERIFIED", "PENDING", "NEEDS_DOCUMENTS"].map((status) => (
              <Button
                key={status}
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void review(status)}
              >
                {status}
              </Button>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
