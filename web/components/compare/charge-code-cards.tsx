"use client";

import { Badge } from "@/components/ui/badge";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { ChargeCode } from "@/lib/api/types";
import {
  CHARGE_CODES,
  chargeCodeAdvice,
  type Purpose,
  type RiskLevel,
} from "@/lib/domain/charge-code";
import { cn } from "@/lib/utils";

const BADGE: Record<RiskLevel, "success" | "warning" | "danger"> = {
  low: "success",
  medium: "warning",
  high: "danger",
};

/**
 * Who pays the fees on the way, as three cards. A fieldset with a legend names the group; the arrow keys
 * move between the cards (a radio group). OUR is the suggestion for tuition.
 */
export function ChargeCodeCards({
  value,
  onChange,
  purpose,
}: {
  value: ChargeCode;
  onChange: (code: ChargeCode) => void;
  purpose: Purpose;
}) {
  return (
    <fieldset className="min-w-0 space-y-2">
      <legend id="charge-legend" className="text-sm leading-none font-medium">
        Charge code
      </legend>
      <p id="charge-help" className="text-muted-foreground text-[13px]">
        Which charge code should I choose? OUR, SHA or BEN decides who pays the fees on the way.
      </p>
      <RadioGroup
        value={value}
        onValueChange={(next) => onChange(next as ChargeCode)}
        aria-labelledby="charge-legend"
        aria-describedby="charge-help"
        className="gap-2"
      >
        {CHARGE_CODES.map((code) => {
          const advice = chargeCodeAdvice(code, purpose);
          const checked = value === code;
          return (
            <label
              key={code}
              htmlFor={`charge-${code}`}
              className={cn(
                "has-[:focus-visible]:ring-ring/50 flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 transition-colors has-[:focus-visible]:ring-[3px]",
                checked ? "border-primary/40 bg-success-soft/60" : "hover:bg-muted/50",
              )}
            >
              <RadioGroupItem id={`charge-${code}`} value={code} className="mt-0.5" />
              <span className="min-w-0 space-y-1">
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="font-mono text-sm font-semibold">{code}</span>
                  <span className="text-muted-foreground text-sm">{advice.who}</span>
                  <Badge variant={BADGE[advice.risk]}>{advice.badge}</Badge>
                </span>
                <span className="text-muted-foreground block text-[13px] leading-relaxed">
                  {advice.explanation}
                </span>
              </span>
            </label>
          );
        })}
      </RadioGroup>
    </fieldset>
  );
}
