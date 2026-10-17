"use client";

import { Plus, Shield, Users } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/app/empty-state";
import { ErrorNotice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { MfaDialog } from "@/components/payment/mfa-dialog";
import { useAuth } from "@/components/providers/auth-provider";
import { RecipientForm } from "@/components/recipients/recipient-form";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
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

const HEAD = "text-muted-foreground text-[11px] font-medium tracking-wider uppercase";

function AllowlistBadge({ allowlisted }: { allowlisted: boolean }) {
  return (
    <Badge variant={allowlisted ? "success" : "warning"} className="gap-1.5">
      <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
      {allowlisted ? "Allowlisted" : "Not allowlisted"}
    </Badge>
  );
}

function LoadingRows() {
  return (
    <TableBody role="status" aria-label="Loading recipients" aria-busy="true">
      {[0, 1].map((row) => (
        <TableRow key={row} className="hover:bg-transparent">
          <TableCell>
            <Skeleton className="h-4 w-48" />
          </TableCell>
          {[0, 1, 2, 3].map((cell) => (
            <TableCell key={cell}>
              <Skeleton className="h-4 w-20" />
            </TableCell>
          ))}
          <TableCell />
        </TableRow>
      ))}
    </TableBody>
  );
}

export function RecipientsScreen() {
  const { user } = useAuth();
  const corridors = useApi<CorridorList>("/corridors");
  const recipients = useApi<{ items: Recipient[] }>("/recipients");
  const [mfaFor, setMfaFor] = useState<{ recipient: Recipient; allowlist: boolean } | null>(null);
  const [removeFor, setRemoveFor] = useState<Recipient | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const formRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadHealth()
      .then((h) => setMfaCode(h.demo?.mfa_code ?? ""))
      .catch(() => undefined);
  }, []);

  /** Bring the Add form into view and put the cursor in its first field. */
  const focusForm = useCallback(() => {
    const target = formRef.current;
    if (!target) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    target
      .querySelector<HTMLElement>("button[role=combobox], input")
      ?.focus({ preventScroll: true });
  }, []);

  // A link to #add opens the page at the form, ready to type.
  const formReady = corridors.data !== null;
  useEffect(() => {
    if (formReady && window.location.hash === "#add") focusForm();
  }, [formReady, focusForm]);

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
      toast.success(allowlist ? "Recipient allowlisted" : "Removed from the allowlist", {
        description: recipient.display_name,
      });
      recipients.reload();
    } catch (e) {
      setError(e as Error);
      toast.error("The allowlist could not be changed");
    }
  }

  if (!user) return null;
  const canAllowlist = user.permissions.includes("recipients:allowlist");
  const items = recipients.data?.items ?? [];
  const allowlisted = items.filter((r) => r.allowlisted).length;
  const loading = recipients.loading && !recipients.data;

  return (
    <div className="space-y-6">
      <PageHead title="Recipients">
        Universities and students you can pay. A recipient must be allowlisted, with a fresh MFA
        code, before a payment to it can be approved.
      </PageHead>
      <ErrorNotice error={recipients.error ?? error} onRetry={recipients.reload} />
      <Card aria-labelledby="recipients-title">
        <CardHeader>
          <CardTitle id="recipients-title" className="flex flex-wrap items-center gap-2 text-base">
            Your recipients
            {recipients.data ? (
              <>
                <Badge variant="muted">
                  {items.length} {items.length === 1 ? "recipient" : "recipients"}
                </Badge>
                <Badge variant="success">{allowlisted} allowlisted</Badge>
              </>
            ) : null}
          </CardTitle>
          <CardAction>
            <Button type="button" variant="outline" size="sm" onClick={focusForm}>
              <Plus aria-hidden="true" />
              Add recipient
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          {recipients.data && items.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No recipients yet."
              description="Add the university below. It must be allowlisted before a payment to it can be approved."
              action={
                <Button type="button" variant="outline" size="sm" onClick={focusForm}>
                  Add a recipient
                </Button>
              }
            />
          ) : (
            <div
              className="overflow-x-auto rounded-md border"
              tabIndex={0}
              role="region"
              aria-label="Recipients table"
            >
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className={HEAD}>Name</TableHead>
                    <TableHead className={HEAD}>Country</TableHead>
                    <TableHead className={HEAD}>BIC</TableHead>
                    <TableHead className={HEAD}>Account (masked)</TableHead>
                    <TableHead className={HEAD}>Allowlist</TableHead>
                    <TableHead className={`${HEAD} text-right`}>
                      Action<span className="sr-only"> (allowlist with MFA, or remove)</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                {loading ? (
                  <LoadingRows />
                ) : (
                  <TableBody>
                    {items.map((r) => (
                      <TableRow key={r.recipient_id}>
                        <TableCell className="min-w-56 whitespace-normal">
                          {/* Rendered as plain text: the UI never injects recipient names as HTML. */}
                          <strong className="font-semibold">{r.display_name}</strong>
                          <div className="text-muted-foreground text-xs">
                            {r.type === "UNIVERSITY" ? "University" : "Student"} - added{" "}
                            {formatDateTime(r.created_at)}
                          </div>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{r.country}</TableCell>
                        <TableCell className="font-mono text-xs">{r.bic}</TableCell>
                        <TableCell className="font-mono text-xs">
                          {r.account_masked}
                          {r.routing_code ? (
                            <div className="text-muted-foreground">routing {r.routing_code}</div>
                          ) : null}
                        </TableCell>
                        <TableCell>
                          <AllowlistBadge allowlisted={r.allowlisted} />
                        </TableCell>
                        <TableCell className="text-right">
                          {canAllowlist && !r.allowlisted ? (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => setMfaFor({ recipient: r, allowlist: true })}
                            >
                              <Shield aria-hidden="true" />
                              Allowlist with MFA
                            </Button>
                          ) : null}
                          {canAllowlist && r.allowlisted ? (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              aria-label={`Remove ${r.display_name} from the allowlist`}
                              onClick={() => setRemoveFor(r)}
                            >
                              Remove
                            </Button>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                )}
              </Table>
            </div>
          )}
          {!canAllowlist ? (
            <p className="text-muted-foreground mt-3 text-sm">
              Only the paying parent can allowlist a recipient.
            </p>
          ) : null}
        </CardContent>
      </Card>
      <div ref={formRef}>
        {corridors.data ? (
          <RecipientForm corridors={corridors.data.items} onCreated={recipients.reload} />
        ) : (
          <Card role="status" aria-label="Loading countries" aria-busy="true">
            <CardHeader>
              <Skeleton className="h-5 w-40" />
            </CardHeader>
            <CardContent className="space-y-3">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </CardContent>
          </Card>
        )}
      </div>
      <AlertDialog open={removeFor !== null} onOpenChange={(open) => !open && setRemoveFor(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove from the allowlist?</AlertDialogTitle>
            <AlertDialogDescription>
              {removeFor?.display_name} will need to be allowlisted again, with a fresh MFA code,
              before a payment to it can be approved. Removing it also needs an MFA code.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (removeFor) setMfaFor({ recipient: removeFor, allowlist: false });
              }}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
