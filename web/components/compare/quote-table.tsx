"use client";

import { Info, MoreHorizontal } from "lucide-react";
import { useState } from "react";

import { Chip } from "@/components/app/status";
import { BreakdownSheet } from "@/components/compare/breakdown-sheet";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Quote, QuoteResult } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  quote: Quote;
  selected: string | null;
  /** "Start payment": the parent picks this provider for the draft. Absent for people who cannot draft. */
  onStart?: (providerId: string) => void;
}

function nameOf(quote: Quote, providerId: string | null): string {
  return quote.results.find((r) => r.provider_id === providerId)?.provider_name ?? "";
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter((part) => /^[A-Za-z]/.test(part))
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/** The five columns of the design, shared by the real table and its placeholder. */
export function QuoteHead({ currency }: { currency: string }) {
  return (
    <TableHeader>
      <TableRow>
        <TableHead>Provider</TableHead>
        <TableHead className="text-right">Exchange rate</TableHead>
        <TableHead className="text-right">Fees</TableHead>
        <TableHead className="text-right">
          <Tooltip>
            <TooltipTrigger className="inline-flex items-center gap-1 underline decoration-dotted underline-offset-4">
              Rate margin
              <Info className="size-3.5" aria-hidden="true" />
            </TooltipTrigger>
            <TooltipContent className="max-w-64">
              The hidden margin: the provider&apos;s rate is worse than the mid-market rate for{" "}
              {currency}. It is a cost even though no fee line shows it.
            </TooltipContent>
          </Tooltip>
        </TableHead>
        <TableHead className="text-right">True total cost</TableHead>
        <TableHead className="w-10">
          <span className="sr-only">Actions</span>
        </TableHead>
      </TableRow>
    </TableHeader>
  );
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

/** F1 provider comparator: ranked by true total cost, with the hidden margin and the fees shown. */
export function QuoteTable({ quote, selected, onStart }: Props) {
  const [breakdownFor, setBreakdownFor] = useState<QuoteResult | null>(null);
  const fit = quote.deadline_fit ?? null;
  const arrival = new Map((fit?.providers ?? []).map((p) => [p.provider_id, p]));
  const highlighted = (r: QuoteResult) => (fit ? fit.best_in_time === r.provider_id : r.rank === 1);
  // Only the length of a decorative bar is worked out here (this cost against the dearest one). Every
  // amount on the screen is the engine's own string.
  const dearest = Math.max(1, ...quote.results.map((r) => r.total_cost_bdt_minor));

  return (
    <div className="space-y-3">
      <DeadlineNote quote={quote} />
      <div
        className="overflow-x-auto rounded-md border"
        tabIndex={0}
        role="region"
        aria-label="Provider comparison table"
      >
        <Table>
          <TableCaption className="sr-only">Providers ranked by true total cost</TableCaption>
          <QuoteHead currency={quote.target.currency} />
          <TableBody className="stagger">
            {quote.results.map((r) => {
              const arrives = arrival.get(r.provider_id);
              const best = highlighted(r);
              return (
                <TableRow
                  key={r.provider_id}
                  data-best={best || undefined}
                  className={cn(
                    "animate-fade transition-colors duration-300",
                    best && "bg-success-soft/70 hover:bg-success-soft/70",
                    !best &&
                      r.shortfall_foreign_minor > 0 &&
                      "bg-danger-soft/50 hover:bg-danger-soft/50",
                  )}
                >
                  <TableCell className="align-top whitespace-normal">
                    <div className="flex items-start gap-3">
                      <Avatar className="mt-0.5 size-8 rounded-md">
                        <AvatarFallback className="rounded-md text-xs font-medium">
                          {initials(r.provider_name)}
                        </AvatarFallback>
                      </Avatar>
                      <div className="min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <strong className="font-medium">{r.provider_name}</strong>
                          {r.rank === 1 && best ? (
                            <Chip tone="ok" className="animate-ring-pulse">
                              Best
                            </Chip>
                          ) : null}
                          {r.rank === 1 && !best ? <Chip tone="neutral">Lowest cost</Chip> : null}
                          {fit && fit.best_in_time === r.provider_id && r.rank !== 1 ? (
                            <Chip tone="ok">Best in time</Chip>
                          ) : null}
                          {onStart && selected === r.provider_id ? (
                            <Chip tone="info">Selected</Chip>
                          ) : null}
                        </div>
                        <div className="text-muted-foreground text-xs">
                          Charge code {r.charge_code}
                          {r.charge_code !== r.requested_charge_code
                            ? ` (you asked for ${r.requested_charge_code})`
                            : ""}
                          {" · "}
                          {r.eta_business_days} business days
                        </div>
                        {arrives ? (
                          <div className="flex flex-wrap items-center gap-1 text-xs">
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
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-right align-top font-mono tabular-nums">
                    {r.display.provider_rate}
                    <div className="text-muted-foreground text-xs">
                      BDT per {quote.target.currency}
                    </div>
                  </TableCell>
                  <TableCell className="text-right align-top font-mono tabular-nums">
                    {r.display.fixed_fee}
                    <div className="text-muted-foreground text-xs">{r.display.swift_fee} SWIFT</div>
                  </TableCell>
                  <TableCell className="text-right align-top font-mono tabular-nums">
                    {r.display.margin_pct}
                    <div className="text-muted-foreground text-xs">{r.display.fx_cost}</div>
                  </TableCell>
                  <TableCell className="text-right align-top font-mono tabular-nums">
                    <span className="font-semibold">{r.display.total_cost}</span>
                    <div className="text-muted-foreground text-xs">
                      {r.display.cost_pct} · you pay {r.display.parent_pays}
                    </div>
                    {r.shortfall_foreign_minor > 0 ? (
                      <Chip tone="danger" role="alert" className="animate-shake mt-1">
                        Short by {r.display.shortfall}
                      </Chip>
                    ) : null}
                    <div
                      aria-hidden="true"
                      className="bg-muted mt-2 ml-auto h-1.5 w-28 overflow-hidden rounded-full"
                    >
                      <div
                        className={cn(
                          "animate-grow-x h-full origin-left rounded-full",
                          best
                            ? "bg-primary"
                            : r.shortfall_foreign_minor > 0
                              ? "bg-destructive"
                              : "bg-primary/45",
                        )}
                        style={{
                          width: `${Math.max(6, Math.round((r.total_cost_bdt_minor / dearest) * 100))}%`,
                        }}
                      />
                    </div>
                  </TableCell>
                  <TableCell className="align-top">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label={`Actions for ${r.provider_name}`}
                        >
                          <MoreHorizontal aria-hidden="true" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => setBreakdownFor(r)}>
                          View breakdown
                        </DropdownMenuItem>
                        {onStart ? (
                          <DropdownMenuItem onSelect={() => onStart(r.provider_id)}>
                            Start payment
                          </DropdownMenuItem>
                        ) : null}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <BreakdownSheet quote={quote} result={breakdownFor} onClose={() => setBreakdownFor(null)} />
    </div>
  );
}
