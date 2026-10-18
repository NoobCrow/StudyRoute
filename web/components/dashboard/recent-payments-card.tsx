"use client";

import { Inbox } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/app/empty-state";
import { ErrorNotice } from "@/components/app/notice";
import { CardSkeleton } from "@/components/app/skeletons";
import { StateBadge } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Page, PaymentBrief } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { formatDateTime } from "@/lib/format";

export function paymentHref(id: string): string {
  return `/payments/view/?id=${encodeURIComponent(id)}`;
}

/** The latest payments, or an empty state that sends the person to Compare. */
export function RecentPaymentsCard({ canCompare }: { canCompare: boolean }) {
  const recent = useApi<Page<PaymentBrief>>("/payments?limit=5");
  const items = recent.data?.items ?? [];
  return (
    <Card aria-labelledby="recent-title" className="flex-1">
      <CardHeader>
        <CardTitle id="recent-title" className="text-base">
          Recent payments
        </CardTitle>
        <CardAction>
          <Link href="/payments/" className="text-primary text-sm font-medium hover:underline">
            See all
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <ErrorNotice error={recent.error} onRetry={recent.reload} />
        {recent.loading && !recent.data ? (
          <CardSkeleton lines={3} label="Loading payments" />
        ) : null}
        {recent.data && items.length === 0 ? (
          <EmptyState
            icon={Inbox}
            className="flex-1"
            title="No payments yet. Start by comparing providers."
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
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Payment</TableHead>
                <TableHead>State</TableHead>
                <TableHead className="text-right">You pay</TableHead>
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
                  <TableCell>
                    <StateBadge state={p.state} />
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {p.parent_pays}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs whitespace-nowrap">
                    {formatDateTime(p.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
}
