"use client";

import { useEffect, useState } from "react";

import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip } from "@/components/app/status";
import { MfaDialog } from "@/components/payment/mfa-dialog";
import { useAuth } from "@/components/providers/auth-provider";
import { RecipientForm } from "@/components/recipients/recipient-form";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { patch } from "@/lib/api/client";
import { loadHealth } from "@/lib/api/health";
import type { CorridorList, Recipient } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { formatDateTime } from "@/lib/format";

export function RecipientsScreen() {
  const { user } = useAuth();
  const corridors = useApi<CorridorList>("/corridors");
  const recipients = useApi<{ items: Recipient[] }>("/recipients");
  const [mfaFor, setMfaFor] = useState<{ recipient: Recipient; allowlist: boolean } | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [mfaCode, setMfaCode] = useState("");

  useEffect(() => {
    loadHealth()
      .then((h) => setMfaCode(h.demo?.mfa_code ?? ""))
      .catch(() => undefined);
  }, []);

  async function applyAllowlist(proof: string) {
    if (!mfaFor) return;
    const { recipient, allowlist } = mfaFor;
    setMfaFor(null);
    setError(null);
    try {
      await patch(
        `/recipients/${recipient.recipient_id}`,
        { allowlisted: allowlist },
        { mfaProof: proof },
      );
      recipients.reload();
    } catch (e) {
      setError(e as Error);
    }
  }

  if (!user) return null;
  const canAllowlist = user.permissions.includes("recipients:allowlist");
  const items = recipients.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHead title="Recipients">
        Universities and students you can pay. A recipient must be allowlisted, with a fresh MFA
        code, before a payment to it can be approved.
      </PageHead>
      <ErrorNotice error={recipients.error ?? error} onRetry={recipients.reload} />
      {recipients.loading && !recipients.data ? (
        <CardSkeleton lines={3} label="Loading recipients" />
      ) : null}
      {items.length > 0 ? (
        <div
          className="bg-card overflow-x-auto rounded-xl border"
          tabIndex={0}
          role="region"
          aria-label="Recipients table"
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Country</TableHead>
                <TableHead>BIC</TableHead>
                <TableHead>Account (masked)</TableHead>
                <TableHead>Allowlist</TableHead>
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((r) => (
                <TableRow key={r.recipient_id}>
                  <TableCell className="whitespace-normal">
                    {/* Rendered as plain text: the UI never injects recipient names as HTML. */}
                    <strong className="font-medium">{r.display_name}</strong>
                    <div className="text-muted-foreground text-xs">
                      {r.type === "UNIVERSITY" ? "University" : "Student"} - added{" "}
                      {formatDateTime(r.created_at)}
                    </div>
                  </TableCell>
                  <TableCell>{r.country}</TableCell>
                  <TableCell className="font-mono text-xs">{r.bic}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {r.account_masked}
                    {r.routing_code ? (
                      <div className="text-muted-foreground">routing {r.routing_code}</div>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    {r.allowlisted ? (
                      <Chip tone="ok">Allowlisted</Chip>
                    ) : (
                      <Chip tone="warn">Not allowlisted</Chip>
                    )}
                  </TableCell>
                  <TableCell>
                    {canAllowlist ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setMfaFor({ recipient: r, allowlist: !r.allowlisted })}
                      >
                        {r.allowlisted ? "Remove from allowlist" : "Allowlist with MFA"}
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {recipients.data && items.length === 0 ? (
        <Notice tone="info">No recipients yet. Add the university below.</Notice>
      ) : null}
      {!canAllowlist ? (
        <p className="text-muted-foreground text-sm">
          Only the paying parent can allowlist a recipient.
        </p>
      ) : null}
      {corridors.data ? (
        <RecipientForm corridors={corridors.data.items} onCreated={recipients.reload} />
      ) : (
        <CardSkeleton lines={4} label="Loading countries" />
      )}
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
