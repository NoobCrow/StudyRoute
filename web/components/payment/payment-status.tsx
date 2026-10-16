import { Ban, CircleCheck, Clock, TriangleAlert, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { PaymentState } from "@/lib/api/types";
import { STATUS_LABEL, statusOf, type PaymentStatus } from "@/lib/domain/payments";

const LOOK: Record<
  PaymentStatus,
  { variant: "info" | "success" | "warning" | "muted"; icon: LucideIcon }
> = {
  in_progress: { variant: "info", icon: Clock },
  completed: { variant: "success", icon: CircleCheck },
  needs_attention: { variant: "warning", icon: TriangleAlert },
  cancelled: { variant: "muted", icon: Ban },
};

/** The status of a payment in the list's four words. Always an icon and text, never colour alone. */
export function PaymentStatusBadge({ state }: { state: PaymentState }) {
  const status = statusOf(state);
  const { variant, icon: Icon } = LOOK[status];
  return (
    <Badge variant={variant} className="gap-1.5">
      <Icon aria-hidden="true" />
      {STATUS_LABEL[status]}
    </Badge>
  );
}
