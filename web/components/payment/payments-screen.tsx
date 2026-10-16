"use client";

import { Inbox } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState } from "@/components/app/empty-state";
import { ErrorNotice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { StateBadge } from "@/components/app/status";
import { paymentHref } from "@/components/dashboard/recent-payments-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { get } from "@/lib/api/client";
import type { Page, PaymentBrief } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { formatDate, formatDateTime } from "@/lib/format";

export function PaymentsScreen() {
  const { user } = useAuth();
  const first = useApi<Page<PaymentBrief>>("/payments?limit=20");
  const [more, setMore] = useState<PaymentBrief[]>([]);
  const [cursor, setCursor] = useState<string | number | null | undefined>(undefined);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);

  const items = [...(first.data?.items ?? []), ...more];
  const next = cursor === undefined ? (first.data?.next_cursor ?? null) : cursor;

  async function loadMore() {
    if (next === null) return;
    setBusy(true);
    setError(null);
    try {
      const page = await get<Page<PaymentBrief>>(
        `/payments?limit=20&cursor=${encodeURIComponent(String(next))}`,
      );
      setMore((m) => [...m, ...page.items]);
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  const canCompare = user?.permissions.includes("quotes:create") ?? false;
  return (
    <div className="space-y-6">
      <PageHead
        title="Payments"
        actions={
          canCompare ? (
            <Button asChild>
              <Link href="/compare/">New comparison</Link>
            </Button>
          ) : null
        }
      >
        Every payment here is simulated. Nothing is sent to a real bank.
      </PageHead>
      <ErrorNotice error={first.error ?? error} onRetry={first.reload} />
      {first.loading && !first.data ? <CardSkeleton lines={4} label="Loading payments" /> : null}
      {first.data && items.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="No payments yet."
          description="Compare providers to start one."
          action={
            canCompare ? (
              <Button asChild variant="outline" size="sm">
                <Link href="/compare/">Compare providers</Link>
              </Button>
            ) : null
          }
        />
      ) : null}
      {items.length > 0 ? (
        <div
          className="bg-card overflow-x-auto rounded-xl border"
          tabIndex={0}
          role="region"
          aria-label="Payments table"
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Recipient and reference</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>State</TableHead>
                <TableHead className="text-right">Beneficiary gets</TableHead>
                <TableHead className="text-right">You pay</TableHead>
                <TableHead>Due</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((p) => (
                <TableRow key={p.payment_id}>
                  <TableCell>
                    <Link
                      href={paymentHref(p.payment_id)}
                      className="text-primary font-medium hover:underline"
                    >
                      {p.recipient_label}
                    </Link>
                    <div className="text-muted-foreground text-xs">{p.reference}</div>
                  </TableCell>
                  <TableCell>{p.provider_name}</TableCell>
                  <TableCell>
                    <StateBadge state={p.state} />
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {p.target.formatted}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {p.parent_pays}
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{formatDate(p.due_date)}</TableCell>
                  <TableCell className="text-muted-foreground text-xs whitespace-nowrap">
                    {formatDateTime(p.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {next !== null && items.length > 0 ? (
        <div>
          <Button type="button" variant="outline" loading={busy} onClick={() => void loadMore()}>
            Load more
          </Button>
        </div>
      ) : null}
    </div>
  );
}
