"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { ErrorNotice, Notice } from "@/components/app/notice";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { post } from "@/lib/api/client";
import type { Payment, Quote, Recipient } from "@/lib/api/types";

const draftSchema = z.object({
  recipientId: z.string().min(1, "Choose a recipient."),
  reference: z
    .string()
    .trim()
    .min(1, "Enter the payment reference.")
    .max(140, "The reference can have at most 140 characters."),
});
type DraftValues = z.infer<typeof draftSchema>;

interface Props {
  quote: Quote;
  providerId: string;
  recipients: Recipient[];
  initialRecipient: string;
}

/** Creates the draft. A draft changes nothing at the bank: the parent still approves with MFA. */
export function DraftForm({ quote, providerId, recipients, initialRecipient }: Props) {
  const router = useRouter();
  const matching = recipients.filter((r) => r.country === quote.destination_country);
  // Never guess who gets the money: preselect only when there is exactly one choice.
  const only = matching.length === 1 ? (matching[0]?.recipient_id ?? "") : "";
  const [error, setError] = useState<Error | null>(null);
  const form = useForm<DraftValues>({
    resolver: zodResolver(draftSchema),
    mode: "onBlur",
    defaultValues: { recipientId: initialRecipient || only, reference: "" },
  });
  const recipientId = useWatch({ control: form.control, name: "recipientId" });
  const reference = useWatch({ control: form.control, name: "reference" });
  const key = useIdempotencyKey(`${quote.quote_id}|${providerId}|${recipientId}|${reference}`);
  const provider =
    quote.results.find((r) => r.provider_id === providerId)?.provider_name ?? providerId;

  async function onSubmit(values: DraftValues) {
    setError(null);
    try {
      const created = await post<Payment>(
        "/payments",
        {
          quote_id: quote.quote_id,
          provider_id: providerId,
          recipient_id: values.recipientId,
          reference: values.reference.trim(),
          due_date: quote.due_date,
        },
        { idempotencyKey: key },
      );
      router.push(`/payments/view/?id=${encodeURIComponent(created.payment_id)}`);
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <Card aria-labelledby="draft-title" className="border-primary/40">
      <CardHeader>
        <CardTitle id="draft-title" className="text-base">
          Create a draft payment
        </CardTitle>
        <CardDescription>
          A draft changes nothing at the bank. You will review the approval summary and approve it
          yourself with MFA.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <ErrorNotice error={error} />
            {matching.length === 0 ? (
              <Notice tone="warn">
                You need a recipient in this country first.{" "}
                <Link href="/recipients/" className="font-medium underline">
                  Add a recipient
                </Link>
                .
              </Notice>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="recipientId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="draft-recipient">Recipient</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger id="draft-recipient" className="w-full">
                          <SelectValue placeholder="Choose a recipient" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {matching.map((r) => (
                          <SelectItem key={r.recipient_id} value={r.recipient_id}>
                            {r.display_name} ({r.account_masked})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="reference"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Payment reference</FormLabel>
                    <FormControl>
                      <Input placeholder="INV-2026-4471 / STU-883201" maxLength={140} {...field} />
                    </FormControl>
                    <FormDescription>
                      Invoice number and student ID, so the university can match the payment.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <Button
              type="submit"
              loading={form.formState.isSubmitting}
              disabled={!recipientId || !reference.trim()}
            >
              Create draft with {provider}
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
