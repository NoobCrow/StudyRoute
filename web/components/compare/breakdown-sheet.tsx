"use client";

import type { ReactNode } from "react";

import { Chip } from "@/components/app/status";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { Quote, QuoteResult } from "@/lib/api/types";

function Line({
  label,
  note,
  children,
  strong = false,
}: {
  label: string;
  note?: string;
  children: ReactNode;
  strong?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 text-sm">
      <dt className="min-w-0">
        <span className={strong ? "font-semibold" : "text-muted-foreground"}>{label}</span>
        {note ? <span className="text-muted-foreground block text-xs">{note}</span> : null}
      </dt>
      <dd
        className={`font-mono tabular-nums ${strong ? "font-semibold" : ""} min-w-0 text-right break-words`}
      >
        {children}
      </dd>
    </div>
  );
}

/**
 * Every line of one provider's cost, as the engine worked it out. Nothing is added up here: each figure
 * is a string the API sent, so the sheet can never disagree with the table.
 */
export function BreakdownSheet({
  quote,
  result,
  onClose,
}: {
  quote: Quote;
  result: QuoteResult | null;
  onClose: () => void;
}) {
  const d = result?.display;
  return (
    <Sheet open={result !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        {result && d ? (
          <>
            <SheetHeader>
              <SheetTitle>{result.provider_name}</SheetTitle>
              <SheetDescription>
                Cost breakdown for {quote.target.formatted} to arrive (synthetic data).
              </SheetDescription>
            </SheetHeader>
            <div className="space-y-3 px-4">
              <dl className="divide-y">
                <Line label="Beneficiary receives">{d.beneficiary_receives}</Line>
                <Line label="Provider rate" note={`Mid-market ${quote.mid_rate.display}`}>
                  {d.provider_rate}
                </Line>
                <Line label="Rate margin" note={`${d.margin_pct} above the mid-market rate`}>
                  {d.fx_cost}
                </Line>
                <Line label="Fixed fee">{d.fixed_fee}</Line>
                <Line label="SWIFT fee">{d.swift_fee}</Line>
                <Line label="Correspondent fee" note="In the destination currency">
                  {d.intermediary_fee}
                </Line>
                <Line label="Receiving fee" note="In the destination currency">
                  {d.receiving_fee}
                </Line>
                <Line label="Charges you cover" note={`Charge code ${result.charge_code}`}>
                  {d.sender_extra}
                </Line>
                <Line label="Short by" note="What the university may not receive">
                  {d.shortfall}
                </Line>
                <Line label="True total cost" note={`${d.cost_pct} of the amount`} strong>
                  {d.total_cost}
                </Line>
                <Line label="You pay" strong>
                  {d.parent_pays}
                </Line>
              </dl>
              {result.charge_code !== result.requested_charge_code ? (
                <p className="text-sm">
                  You asked for {result.requested_charge_code}; this provider used{" "}
                  {result.charge_code}.
                </p>
              ) : null}
              {result.warnings.map((warning) => (
                <p key={warning.code} className="text-destructive text-sm" role="alert">
                  {warning.message}
                </p>
              ))}
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <Chip tone="neutral">{result.eta_business_days} business days</Chip>
                <span className="text-muted-foreground">
                  to arrive, by the provider&apos;s terms
                </span>
              </p>
            </div>
            <SheetFooter>
              <p className="text-muted-foreground text-xs">
                Indicative. Confirm with your AD bank. {quote.disclaimer}
              </p>
            </SheetFooter>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
