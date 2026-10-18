"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { REGEXP_ONLY_DIGITS } from "input-otp";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
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
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { post } from "@/lib/api/client";

export type MfaScope =
  | "approve_payment"
  | "allowlist_recipient"
  | "confirm_bank_transfer"
  | "confirm_escrow"
  | "release_escrow"
  | "cancel_escrow"
  | "review_payment";

const CODE_LENGTH = 6;
const codeSchema = z.object({
  code: z.string().regex(/^[0-9]{6}$/, "Enter the 6-digit code from your authenticator app."),
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

/**
 * Step-up MFA in six boxes. The proof returned is bound to this user, this action and this subject.
 * The dialog traps focus and gives it back to the button that opened it when it closes.
 */
export function MfaDialog({ title, scope, subjectId, sandboxCode, onProof, onCancel }: Props) {
  const [error, setError] = useState<Error | null>(null);
  // This dialog has no Radix trigger, so remember the button that opened it and give focus back to it.
  const [opener] = useState(() =>
    typeof document === "undefined" ? null : document.activeElement,
  );
  const form = useForm<CodeValues>({
    resolver: zodResolver(codeSchema),
    mode: "onSubmit",
    defaultValues: { code: "" },
  });
  const code = useWatch({ control: form.control, name: "code" });

  async function onSubmit(values: CodeValues) {
    setError(null);
    try {
      const result = await post<{ mfa_proof: string }>("/auth/mfa/verify", {
        code: values.code,
        scope,
        subject_id: subjectId,
      });
      onProof(result.mfa_proof);
    } catch (e) {
      setError(e as Error);
      form.reset({ code: "" });
      form.setFocus("code");
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          if (opener instanceof HTMLElement) opener.focus();
        }}
        onOpenAutoFocus={(event) => {
          // Focus the first box here, not with autoFocus: the dialog must see which button opened it.
          event.preventDefault();
          form.setFocus("code");
        }}
      >
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
                    <InputOTP
                      maxLength={CODE_LENGTH}
                      inputMode="numeric"
                      pattern={REGEXP_ONLY_DIGITS}
                      autoComplete="one-time-code"
                      containerClassName="justify-center"
                      {...field}
                    >
                      <InputOTPGroup>
                        {Array.from({ length: CODE_LENGTH }, (_, index) => (
                          <InputOTPSlot key={index} index={index} />
                        ))}
                      </InputOTPGroup>
                    </InputOTP>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onCancel}>
                Cancel
              </Button>
              <Button
                type="submit"
                loading={form.formState.isSubmitting}
                disabled={code.length !== CODE_LENGTH}
              >
                Confirm
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
