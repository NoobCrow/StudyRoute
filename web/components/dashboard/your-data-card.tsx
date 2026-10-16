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
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { post } from "@/lib/api/client";
import { useInvalidateApi } from "@/lib/api/use-api";

interface ResetResult {
  reset: boolean;
  deleted: Record<string, number>;
}

/** "Reset my data" (blueprint 12.4). A confirmation first, because it cannot be undone. */
export function YourDataCard() {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const invalidate = useInvalidateApi();

  async function reset() {
    setBusy(true);
    setError(null);
    try {
      const result = await post<ResetResult>("/me/reset");
      const counts = Object.entries(result.deleted)
        .map(([name, count]) => `${count} ${name}`)
        .join(", ");
      toast.success("Your data was deleted", {
        description: `${counts || "Nothing to delete"}. Add a recipient again before creating a new payment.`,
      });
      setOpen(false);
      await invalidate();
    } catch (e) {
      setError(e as Error);
      toast.error("The data could not be deleted");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card aria-labelledby="reset-title">
      <CardHeader>
        <CardTitle id="reset-title" className="text-base">
          Your data
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-muted-foreground text-sm leading-relaxed">
          This is a sandbox with synthetic data. You can delete your payments, quotes, recipients
          and documents at any time. The audit log keeps its entries, which hold no personal
          details.
        </p>
        <ErrorNotice error={error} />
        <AlertDialog open={open} onOpenChange={setOpen}>
          <AlertDialogTrigger asChild>
            <Button type="button" variant="destructive-outline">
              Reset my data
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete all of your data?</AlertDialogTitle>
              <AlertDialogDescription>
                Your payments, quotes, recipients and documents will be deleted. This cannot be
                undone. The audit log keeps its entries.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep it</AlertDialogCancel>
              <AlertDialogAction
                variant="destructive"
                disabled={busy}
                onClick={(event) => {
                  event.preventDefault();
                  void reset();
                }}
              >
                {busy ? "Deleting..." : "Yes, delete my data"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );
}
