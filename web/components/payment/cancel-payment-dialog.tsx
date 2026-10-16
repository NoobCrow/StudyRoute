"use client";

import { useState } from "react";
import { toast } from "sonner";

import { ErrorNotice } from "@/components/app/notice";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { post } from "@/lib/api/client";
import type { PaymentBrief } from "@/lib/api/types";

/** Asks first, then cancels. The Idempotency-Key makes a second click or a retry cancel it once. */
export function CancelPaymentDialog({
  payment,
  onClose,
  onCancelled,
}: {
  payment: PaymentBrief | null;
  onClose: () => void;
  onCancelled: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const key = useIdempotencyKey(`cancel:${payment?.payment_id ?? ""}`);

  async function cancel() {
    if (!payment) return;
    setBusy(true);
    setError(null);
    try {
      await post(
        `/payments/${encodeURIComponent(payment.payment_id)}/cancel`,
        {},
        { idempotencyKey: key },
      );
      toast.success("Payment cancelled", {
        description: `${payment.reference} was cancelled. Nothing was sent.`,
      });
      onCancelled();
    } catch (e) {
      setError(e as Error);
      toast.error("The payment could not be cancelled");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AlertDialog
      open={payment !== null}
      onOpenChange={(open) => {
        if (!open) {
          setError(null);
          onClose();
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Cancel this payment?</AlertDialogTitle>
          <AlertDialogDescription>
            {payment?.reference} to {payment?.recipient_label} will be cancelled. This is a
            simulation: nothing was sent to a real bank, and a cancelled payment cannot be started
            again.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <ErrorNotice error={error} />
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={busy}
            onClick={(event) => {
              event.preventDefault();
              void cancel();
            }}
          >
            {busy ? "Cancelling..." : "Cancel payment"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
