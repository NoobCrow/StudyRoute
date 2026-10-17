"use client";

import type { Ref } from "react";

import { ErrorNotice } from "@/components/app/notice";
import { Chip } from "@/components/app/status";
import { Countdown } from "@/components/compare/countdown";
import { QuoteHead, QuoteTable } from "@/components/compare/quote-table";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import type { Quote } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Three grey rows with the shape of a quote. Still while nothing was asked, pulsing while we wait. */
function PlaceholderRows({ busy }: { busy: boolean }) {
  const pulse = busy ? "" : "animate-none";
  return (
    <TableBody aria-hidden="true">
      {[0, 1, 2].map((row) => (
        <TableRow key={row} className="hover:bg-transparent">
          <TableCell>
            <div className="flex items-center gap-3">
              <Skeleton className={cn("size-8 rounded-md", pulse)} />
              <Skeleton className={cn("h-3.5 w-28", pulse)} />
            </div>
          </TableCell>
          {[0, 1, 2, 3].map((cell) => (
            <TableCell key={cell} className="text-right">
              <Skeleton className={cn("ml-auto h-3.5 w-16", pulse)} />
            </TableCell>
          ))}
          <TableCell />
        </TableRow>
      ))}
    </TableBody>
  );
}

interface Props {
  quote: Quote | null;
  busy: boolean;
  error: Error | null;
  currency: string;
  selected: string | null;
  onStart?: (providerId: string) => void;
  onRetry: () => void;
  /** The results heading takes focus after Get quotes, so a keyboard or screen reader user lands here. */
  headingRef: Ref<HTMLDivElement>;
}

/** The ranked quotes, with loading, empty and error states. */
export function QuotesCard({
  quote,
  busy,
  error,
  currency,
  selected,
  onStart,
  onRetry,
  headingRef,
}: Props) {
  const showTable = quote !== null && !busy;
  return (
    <Card aria-labelledby="results-title">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle
            id="results-title"
            ref={headingRef}
            tabIndex={-1}
            className="text-base outline-none"
          >
            Quotes
          </CardTitle>
          <Chip tone="neutral">Ranked by true total cost</Chip>
          {quote ? <Countdown expiresAt={quote.expires_at} /> : null}
        </div>
        <CardAction className="text-muted-foreground self-center text-xs">
          Synthetic data
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorNotice error={error} onRetry={onRetry} />
        {showTable ? (
          <>
            <p className="text-muted-foreground text-xs">
              Mid-market rate {quote.mid_rate.display} ({quote.mid_rate.source}, as of{" "}
              {quote.mid_rate.as_of}). {quote.disclaimer}
            </p>
            <QuoteTable quote={quote} selected={selected} onStart={onStart} />
            <p className="text-muted-foreground text-xs">
              Quote {quote.quote_id}. Input hash {quote.input_hash.slice(0, 18)}...
            </p>
          </>
        ) : (
          <div role={busy ? "status" : undefined} aria-busy={busy || undefined}>
            {busy ? <span className="sr-only">Asking the synthetic providers</span> : null}
            <div className="overflow-x-auto">
              <Table>
                <QuoteHead currency={currency} />
                <PlaceholderRows busy={busy} />
              </Table>
            </div>
            {busy ? null : (
              <p className="text-muted-foreground py-3 text-center text-sm">
                No quotes yet. Press Get quotes to rank providers by the true total cost.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
