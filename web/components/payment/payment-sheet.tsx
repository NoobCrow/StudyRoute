"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { paymentHref } from "@/components/dashboard/recent-payments-card";
import { PaymentStatusBadge } from "@/components/payment/payment-status";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { PaymentBrief } from "@/lib/api/types";
import { canCancel } from "@/lib/domain/payments";
import { formatDate, formatDateTime } from "@/lib/format";

function Line({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right break-words">{children}</dd>
    </div>
  );
}

/** One payment from the list, in a side sheet. Approving and tracking stay on the full page. */
export function PaymentSheet({
  payment,
  mayCancel,
  onClose,
  onCancel,
}: {
  payment: PaymentBrief | null;
  mayCancel: boolean;
  onClose: () => void;
  onCancel: (payment: PaymentBrief) => void;
}) {
  return (
    <Sheet open={payment !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        {payment ? (
          <>
            <SheetHeader>
              <SheetTitle className="font-mono text-base">{payment.reference}</SheetTitle>
              <SheetDescription>Simulated. Nothing was sent to a real bank.</SheetDescription>
            </SheetHeader>
            <dl className="divide-y px-4">
              <Line label="Status">
                <PaymentStatusBadge state={payment.state} />
                <span className="text-muted-foreground mt-1 block text-xs">
                  {payment.state.replace(/_/g, " ").toLowerCase()}
                </span>
              </Line>
              <Line label="Recipient">{payment.recipient_label}</Line>
              <Line label="Provider">{payment.provider_name}</Line>
              <Line label="Beneficiary receives">
                <span className="font-mono tabular-nums">{payment.target.formatted}</span>
              </Line>
              <Line label="You pay">
                <span className="font-mono tabular-nums">{payment.parent_pays}</span>
              </Line>
              <Line label="University due date">{formatDate(payment.due_date)}</Line>
              <Line label="Created">{formatDateTime(payment.created_at)}</Line>
              <Line label="Updated">{formatDateTime(payment.updated_at)}</Line>
              {payment.uetr ? (
                <Line label="UETR">
                  <span className="font-mono text-xs break-all">{payment.uetr}</span>
                </Line>
              ) : null}
            </dl>
            <SheetFooter className="sm:flex-row">
              <Button asChild>
                <Link href={paymentHref(payment.payment_id)}>Open the full page</Link>
              </Button>
              {mayCancel && canCancel(payment.state) ? (
                <Button
                  type="button"
                  variant="destructive-outline"
                  onClick={() => onCancel(payment)}
                >
                  Cancel payment
                </Button>
              ) : null}
            </SheetFooter>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
