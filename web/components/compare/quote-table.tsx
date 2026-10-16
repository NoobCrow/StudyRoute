"use client";

import { Chip } from "@/components/app/status";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Quote, QuoteResult } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  quote: Quote;
  selected: string | null;
  onSelect?: (providerId: string) => void;
}

function Shortfall({ result }: { result: QuoteResult }) {
  if (result.shortfall_foreign_minor <= 0)
    return <span className="text-muted-foreground">None</span>;
  return (
    <Chip tone="danger" role="alert">
      Short by {result.display.shortfall}
    </Chip>
  );
}

function nameOf(quote: Quote, providerId: string | null): string {
  return quote.results.find((r) => r.provider_id === providerId)?.provider_name ?? "";
}

/** One sentence that says what the deadline changed, built from the engine's answer. */
function DeadlineNote({ quote }: { quote: Quote }) {
  const fit = quote.deadline_fit;
  if (!fit) return null;
  if (fit.best_in_time === null) {
    return (
      <p className="text-destructive text-sm" role="alert">
        No provider can arrive by {formatDate(fit.due_date)} if the money is sent on{" "}
        {formatDate(fit.send_date)}. The fastest is {nameOf(quote, fit.fastest)}. Ask the university
        whether it can wait.
      </p>
    );
  }
  if (fit.cheapest_misses_deadline) {
    return (
      <p className="text-destructive text-sm" role="alert">
        {nameOf(quote, fit.cheapest_overall)} has the lowest cost but would arrive after{" "}
        {formatDate(fit.due_date)}. The cheapest provider that arrives in time is{" "}
        {nameOf(quote, fit.best_in_time)}.
      </p>
    );
  }
  return (
    <p className="text-muted-foreground text-sm" role="status">
      The lowest-cost provider also arrives by {formatDate(fit.due_date)}. {fit.indicative}
    </p>
  );
}

/** F1 provider comparator: ranked by true total cost percentage, hidden margin included. */
export function QuoteTable({ quote, selected, onSelect }: Props) {
  const fit = quote.deadline_fit ?? null;
  const arrival = new Map((fit?.providers ?? []).map((p) => [p.provider_id, p]));
  const highlighted = (r: QuoteResult) => (fit ? fit.best_in_time === r.provider_id : r.rank === 1);

  const table = (
    <Table>
      <TableCaption className="sr-only">
        Providers ranked by true total cost percentage
      </TableCaption>
      <TableHeader>
        <TableRow>
          {onSelect ? (
            <TableHead>
              <span className="sr-only">Choose</span>
            </TableHead>
          ) : null}
          <TableHead>Rank</TableHead>
          <TableHead>Provider</TableHead>
          <TableHead className="text-right">Rate (BDT per {quote.target.currency})</TableHead>
          <TableHead className="text-right">Hidden margin</TableHead>
          <TableHead>Shortfall risk</TableHead>
          <TableHead className="text-right">Total cost</TableHead>
          <TableHead className="text-right">Cost %</TableHead>
          <TableHead className="text-right">You pay</TableHead>
          <TableHead className="text-right">Days</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {quote.results.map((r) => {
          const arrives = arrival.get(r.provider_id);
          return (
            <TableRow
              key={r.provider_id}
              data-best={highlighted(r) || undefined}
              className={cn(
                highlighted(r) && "bg-success-soft/70 hover:bg-success-soft/70",
                !highlighted(r) &&
                  r.shortfall_foreign_minor > 0 &&
                  "bg-danger-soft/50 hover:bg-danger-soft/50",
              )}
            >
              {onSelect ? (
                <TableCell>
                  <RadioGroupItem value={r.provider_id} aria-label={`Choose ${r.provider_name}`} />
                </TableCell>
              ) : null}
              <TableCell className="align-top">
                {r.rank}
                <div className="mt-1 flex flex-col items-start gap-1">
                  {r.rank === 1 ? <Chip tone="ok">Lowest cost</Chip> : null}
                  {fit && fit.best_in_time === r.provider_id && r.rank !== 1 ? (
                    <Chip tone="ok">Best in time</Chip>
                  ) : null}
                </div>
              </TableCell>
              <TableCell className="align-top whitespace-normal">
                <strong className="font-medium">{r.provider_name}</strong>
                <div className="text-muted-foreground text-xs">
                  Charge code {r.charge_code}
                  {r.charge_code !== r.requested_charge_code
                    ? ` (you asked for ${r.requested_charge_code})`
                    : ""}
                </div>
                {arrives ? (
                  <div className="mt-1 flex flex-wrap items-center gap-1 text-xs">
                    Arrives {formatDate(arrives.arrives_on)}{" "}
                    <Chip tone={arrives.meets_deadline ? "ok" : "danger"}>
                      {arrives.meets_deadline ? "In time" : "Too late"}
                    </Chip>
                  </div>
                ) : null}
                {r.warnings.map((w) => (
                  <div key={w.code} className="text-destructive text-xs">
                    {w.message}
                  </div>
                ))}
              </TableCell>
              <TableCell className="text-right align-top font-mono tabular-nums">
                {r.display.provider_rate}
              </TableCell>
              <TableCell className="text-right align-top font-mono tabular-nums">
                {r.display.margin_pct}
              </TableCell>
              <TableCell className="align-top">
                <Shortfall result={r} />
              </TableCell>
              <TableCell className="text-right align-top font-mono tabular-nums">
                {r.display.total_cost}
              </TableCell>
              <TableCell className="text-right align-top font-mono font-semibold tabular-nums">
                {r.display.cost_pct}
              </TableCell>
              <TableCell className="text-right align-top font-mono tabular-nums">
                {r.display.parent_pays}
              </TableCell>
              <TableCell className="text-right align-top font-mono tabular-nums">
                {r.eta_business_days}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );

  return (
    <div className="space-y-3">
      <DeadlineNote quote={quote} />
      <div
        className="overflow-x-auto rounded-md border"
        tabIndex={0}
        role="region"
        aria-label="Provider comparison table"
      >
        {onSelect ? (
          <RadioGroup value={selected ?? ""} onValueChange={onSelect} aria-label="Provider">
            {table}
          </RadioGroup>
        ) : (
          table
        )}
      </div>
    </div>
  );
}
