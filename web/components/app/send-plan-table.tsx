import { Chip } from "@/components/app/status";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { SendPlan } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** The smart send plan: the same money sent monthly, quarterly, per term or all at once. */
export function SendPlanTable({ plan, compact = false }: { plan: SendPlan; compact?: boolean }) {
  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-sm">
        {plan.total.formatted} over {plan.months} months. Totals are the true cost in BDT, from the
        engine.
      </p>
      <div
        className="overflow-x-auto rounded-md border"
        tabIndex={0}
        role="region"
        aria-label="Send plan comparison table"
      >
        <Table>
          <TableCaption className="sr-only">
            True total cost of each way of sending the money
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Way of sending</TableHead>
              <TableHead className="text-right">Transfers</TableHead>
              {compact ? null : <TableHead>Cheapest provider</TableHead>}
              <TableHead className="text-right">Total cost</TableHead>
              <TableHead className="text-right">Saves</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {plan.options.map((o) => (
              <TableRow
                key={o.key}
                className={cn(o.key === plan.cheapest_key && "bg-success-soft/60")}
              >
                <TableCell>
                  <strong className="font-medium">{o.label}</strong>
                  <div className="text-muted-foreground text-xs">{o.display.per_transfer} each</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {o.key === plan.cheapest_key ? <Chip tone="ok">Cheapest on paper</Chip> : null}
                    {o.exceeds_sandbox_cap ? <Chip tone="warn">Over the sandbox cap</Chip> : null}
                  </div>
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">{o.transfers}</TableCell>
                {compact ? null : <TableCell>{o.provider_name}</TableCell>}
                <TableCell className="text-right font-mono tabular-nums">
                  {o.display.total_cost}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {o.key === "monthly" ? "-" : o.display.saving_vs_monthly}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <p className="text-sm">{plan.trade_off}</p>
      <p className="text-muted-foreground text-xs">{plan.disclaimer}</p>
    </div>
  );
}
