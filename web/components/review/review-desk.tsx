"use client";

import { Gavel } from "lucide-react";
import Link from "next/link";

import { ErrorNotice } from "@/components/app/notice";
import { EmptyState } from "@/components/app/empty-state";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip } from "@/components/app/status";
import {
  ClockChip,
  PriorityChip,
  ReviewStatusChip,
  clockText,
} from "@/components/review/review-bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ReviewQueue } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-muted-foreground text-sm font-normal">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold">{value}</p>
        {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

/** The bank reviewer's queue: the most overdue first, then the model's priority hint. */
export function ReviewDesk() {
  const queue = useApi<ReviewQueue>("/bank-review/queue", { refetchInterval: 10000 });
  const data = queue.data;
  return (
    <div className="space-y-6">
      <PageHead title="Bank review desk">
        Payments that wait for a person at the sandbox bank. Most payments never appear here: with
        no reason to look closer they take the fast lane. You decide; nothing on this page can
        approve for you.
      </PageHead>
      <ErrorNotice error={queue.error} onRetry={queue.reload} />
      {!data ? (
        <CardSkeleton lines={4} label="Loading the queue" />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Waiting" value={String(data.stats.waiting)} />
            <Stat
              label="Past the target time"
              value={String(data.stats.overdue)}
              hint={`Target: ${data.stats.target_hours} hours`}
            />
            <Stat
              label="Average time to decide"
              value={
                data.stats.average_hours_to_decide === null
                  ? "none yet"
                  : `${data.stats.average_hours_to_decide} h`
              }
              hint={`${data.stats.decided} decided`}
            />
          </div>
          {data.items.length === 0 ? (
            <EmptyState
              icon={Gavel}
              title="Nothing is waiting for the bank"
              description="Payments that need a person will show up here after a parent requests approval."
            />
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Payment</TableHead>
                      <TableHead>Amount</TableHead>
                      <TableHead>Why flagged</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Clock</TableHead>
                      <TableHead>Priority</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((item) => (
                      <TableRow key={item.payment_id}>
                        <TableCell>
                          <Link
                            className="text-primary underline"
                            href={`/payments/view/?id=${encodeURIComponent(item.payment_id)}`}
                          >
                            Open brief
                          </Link>
                        </TableCell>
                        <TableCell>
                          {item.amount.formatted}
                          <span className="text-muted-foreground block text-xs">
                            {item.purpose.toLowerCase()}
                          </span>
                        </TableCell>
                        <TableCell className="max-w-56 whitespace-normal">
                          {item.signals.join(", ") || "none"}
                        </TableCell>
                        <TableCell>
                          <ReviewStatusChip status={item.status} />
                        </TableCell>
                        <TableCell className="space-y-1">
                          <ClockChip clock={item.clock} />
                          {item.escalated ? <Chip tone="danger">reminded</Chip> : null}
                          <span className="text-muted-foreground block text-xs">
                            {clockText(item.clock) ?? ""}
                          </span>
                        </TableCell>
                        <TableCell>
                          <PriorityChip priority={item.priority} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
          <p className="text-muted-foreground text-xs">{data.disclaimer}</p>
        </>
      )}
    </div>
  );
}
