"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ErrorNotice } from "@/components/app/notice";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { post } from "@/lib/api/client";

export type MfaScope =
  | "approve_payment"
  | "allowlist_recipient"
  | "confirm_bank_transfer"
  | "confirm_escrow"
  | "release_escrow"
  | "cancel_escrow";

const codeSchema = z.object({
  code: z
    .string()
    .trim()
    .min(4, "Enter the code from your authenticator app.")
    .max(12, "The code is too long."),
});
type CodeValues = z.infer<typeof codeSchema>;

interface Props {
  title: string;
  scope: MfaScope;
  subjectId: string;
  sandboxCode?: string;
  onProof: (proof: string) => void;
  onCancel: () => void;
}

/** Step-up MFA. The proof returned is bound to this user, this action and this subject. */
export function MfaDialog({ title, scope, subjectId, sandboxCode, onProof, onCancel }: Props) {
  const [error, setError] = useState<Error | null>(null);
  const form = useForm<CodeValues>({
    resolver: zodResolver(codeSchema),
    mode: "onBlur",
    defaultValues: { code: "" },
  });

  async function onSubmit(values: CodeValues) {
    setError(null);
    try {
      const result = await post<{ mfa_proof: string }>("/auth/mfa/verify", {
        code: values.code.trim(),
        scope,
        subject_id: subjectId,
      });
      onProof(result.mfa_proof);
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <DialogHeader>
              <DialogTitle>{title}</DialogTitle>
              <DialogDescription>
                Enter the 6-digit code from your authenticator app. The proof lasts 5 minutes and
                works once, for this action only.
              </DialogDescription>
            </DialogHeader>
            {sandboxCode ? (
              <p className="text-sm">
                Sandbox hint: the demo code is <code className="font-mono">{sandboxCode}</code>.
              </p>
            ) : null}
            <ErrorNotice error={error} />
            <FormField
              control={form.control}
              name="code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>MFA code</FormLabel>
                  <FormControl>
                    <Input
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={12}
                      className="font-mono"
                      autoFocus
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onCancel}>
                Cancel
              </Button>
              <Button type="submit" loading={form.formState.isSubmitting}>
                Verify
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
