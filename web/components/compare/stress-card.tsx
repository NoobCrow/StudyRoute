"use client";

import { ErrorNotice } from "@/components/app/notice";
import { Loading } from "@/components/app/skeletons";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { StressTest } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";

/** Currency-drop stress test: the chosen quote priced again if the taka weakens. The engine does the maths. */
export function StressCard({ quoteId, providerId }: { quoteId: string; providerId: string }) {
  const stress = useApi<StressTest>(
    `/quotes/${quoteId}/stress?provider_id=${encodeURIComponent(providerId)}`,
  );
  const data = stress.data;
  return (
    <Card aria-labelledby="stress-title">
      <CardHeader>
        <CardTitle id="stress-title" className="text-base">
          Currency-drop stress test
        </CardTitle>
        <CardDescription>
          What if the taka weakens before you send? Same provider, same fees, with each{" "}
          {data?.target.currency ?? "foreign unit"} costing more taka.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorNotice error={stress.error} onRetry={stress.reload} />
        {stress.loading && !data ? <Loading what="Pricing the what-if" /> : null}
        {data ? (
          <>
            <div
              className="overflow-x-auto rounded-md border"
              tabIndex={0}
              role="region"
              aria-label="Currency-drop stress test table"
            >
              <Table>
                <TableCaption className="sr-only">
                  {data.provider_name}: what you would pay if the taka weakens
                </TableCaption>
                <TableHeader>
                  <TableRow>
                    <TableHead>If each {data.target.currency} costs</TableHead>
                    <TableHead className="text-right">
                      Rate (BDT per {data.target.currency})
                    </TableHead>
                    <TableHead className="text-right">You would pay</TableHead>
                    <TableHead className="text-right">Extra</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableHead scope="row">Today</TableHead>
                    <TableCell className="text-right font-mono tabular-nums">
                      {data.baseline.display.provider_rate}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {data.baseline.display.parent_pays}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-right">None</TableCell>
                  </TableRow>
                  {data.scenarios.map((row) => (
                    <TableRow key={row.drop_pct}>
                      <TableHead scope="row">{row.drop_pct} more taka</TableHead>
                      <TableCell className="text-right font-mono tabular-nums">
                        {row.display.provider_rate}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {row.display.parent_pays}
                      </TableCell>
                      <TableCell className="text-destructive text-right font-mono tabular-nums">
                        {row.display.extra} ({row.display.extra_pct})
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="text-muted-foreground text-xs">
              {data.assumption} {data.note}
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
