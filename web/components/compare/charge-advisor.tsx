import { ChevronRight } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { ChargeCode } from "@/lib/api/types";

const CHARGE_HELP: Record<ChargeCode, string> = {
  OUR: "You pay every fee. The university should receive the full invoice amount. Best for tuition.",
  SHA: "You pay your bank. Correspondent and receiving fees are taken from the amount, so the university may receive less.",
  BEN: "The beneficiary pays everything. This has the highest risk of a short payment.",
};

/** Which charge code to choose. Opens by itself when the person picks something other than OUR. */
export function ChargeAdvisor({ value }: { value: ChargeCode }) {
  return (
    <Collapsible defaultOpen={value !== "OUR"} key={value === "OUR" ? "our" : "other"}>
      <CollapsibleTrigger className="group text-muted-foreground hover:text-foreground flex items-center gap-1 text-sm">
        <ChevronRight
          className="size-4 transition-transform group-data-[state=open]:rotate-90"
          aria-hidden="true"
        />
        Which charge code should I choose? (OUR, SHA, BEN)
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-2 space-y-1 pl-5 text-sm">
          {(Object.keys(CHARGE_HELP) as ChargeCode[]).map((code) => (
            <li key={code}>
              <strong>{code}</strong>
              {code === "OUR" ? " (recommended for tuition)" : ""}: {CHARGE_HELP[code]}
            </li>
          ))}
        </ul>
        <p className="text-muted-foreground mt-2 pl-5 text-sm">
          Check the university&apos;s own payment instructions too. Indicative. Confirm with your AD
          bank.
        </p>
      </CollapsibleContent>
    </Collapsible>
  );
}
