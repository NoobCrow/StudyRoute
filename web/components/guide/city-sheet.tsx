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
import type { BudgetCity, Money } from "@/lib/api/types";

function Line({
  label,
  children,
  strong = false,
}: {
  label: string;
  children: ReactNode;
  strong?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 text-sm">
      <dt className={strong ? "font-semibold" : "text-muted-foreground"}>{label}</dt>
      <dd
        className={`min-w-0 text-right font-mono break-words tabular-nums ${strong ? "font-semibold" : ""}`}
      >
        {children}
      </dd>
    </div>
  );
}

/**
 * One month in one city, line by line, as the engine added it up. Nothing is added here: every figure is
 * a string the API sent, so the sheet can never disagree with the table.
 */
export function CitySheet({
  city,
  housingLabel,
  budget,
  disclaimer,
  onClose,
}: {
  city: BudgetCity | null;
  housingLabel: string;
  budget: Money | null;
  disclaimer: string;
  onClose: () => void;
}) {
  return (
    <Sheet open={city !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        {city ? (
          <>
            <SheetHeader>
              <SheetTitle>
                {city.city}, {city.country_name}
              </SheetTitle>
              <SheetDescription>
                A month for {housingLabel.toLowerCase()}. Invented figures for the sandbox.
              </SheetDescription>
            </SheetHeader>
            <div className="space-y-3 px-4">
              <dl className="divide-y">
                {city.lines.map((line) => (
                  <Line key={line.key} label={line.label}>
                    {line.formatted}
                  </Line>
                ))}
                <Line label="A month in all" strong>
                  {city.total.formatted}
                </Line>
                <Line label={`In taka at ${city.rate_bdt_per_unit} BDT per ${city.currency}`}>
                  {city.total_bdt.formatted}
                </Line>
                <Line label="Rent alone, in taka">{city.rent_bdt.formatted}</Line>
                <Line label="Rent as a share of the month">{city.rent_share_pct}%</Line>
              </dl>
              {budget && city.fits !== null ? (
                <p className="text-sm">
                  <Chip tone={city.fits ? "ok" : "warn"}>
                    {city.fits
                      ? `Fits, ${city.spare_bdt?.formatted ?? ""} to spare`
                      : `Short by ${city.gap_bdt?.formatted ?? ""}`}
                  </Chip>{" "}
                  <span className="text-muted-foreground">
                    against your budget of {budget.formatted} a month
                  </span>
                </p>
              ) : null}
            </div>
            <SheetFooter className="text-muted-foreground text-xs">{disclaimer}</SheetFooter>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
