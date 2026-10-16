"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, type Resolver, useWatch } from "react-hook-form";
import { z } from "zod";

import { DatePicker } from "@/components/app/date-picker";
import { ErrorNotice } from "@/components/app/notice";
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
import type { CorridorList, Recipient } from "@/lib/api/types";
import { formDefaults } from "@/lib/corridors";
import { addDaysIso } from "@/lib/format";
import { parseMajorToMinor } from "@/lib/money";
import { moneyText } from "@/lib/schemas/money";

type Purpose = "TUITION" | "LIVING";

function schemaFor(exponent: number) {
  return z.object({
    recipientId: z.string().min(1, "Choose who gets paid."),
    purpose: z.enum(["TUITION", "LIVING"]),
    amount: moneyText("Total", () => exponent),
    tranches: z.string().superRefine((value, ctx) => {
      const count = Number(value);
      if (!/^[0-9]+$/.test(value.trim()) || count < 1 || count > 24) {
        ctx.addIssue({ code: "custom", message: "Use 1 to 24 tranches." });
      }
    }),
    first: z.string().min(1, "Choose the first payment date."),
    reference: z.string().trim().min(1, "Enter a reference.").max(70, "At most 70 characters."),
  });
}
type Values = z.infer<ReturnType<typeof schemaFor>>;

interface Props {
  recipients: Recipient[];
  corridors: CorridorList;
  onPlanned: () => void;
}

/** Plan an escrow: pick who gets paid, how much, and when. Nothing is locked until MFA confirms it. */
export function EscrowPlanForm({ recipients, corridors, onPlanned }: Props) {
  const [error, setError] = useState<Error | null>(null);
  const resolver: Resolver<Values> = (values, context, options) => {
    const recipient = recipients.find((r) => r.recipient_id === values.recipientId);
    const corridor = corridors.items.find((c) => c.country === recipient?.country);
    return zodResolver(schemaFor(corridor?.exponent ?? 2))(values, context, options);
  };
  const form = useForm<Values>({
    resolver,
    mode: "onBlur",
    defaultValues: {
      recipientId: recipients[0]?.recipient_id ?? "",
      purpose: "TUITION",
      amount: "",
      tranches: "1",
      first: addDaysIso(14),
      reference: "",
    },
  });
  const [recipientId, purpose, tranches, amount, first, reference] = useWatch({
    control: form.control,
    name: ["recipientId", "purpose", "tranches", "amount", "first", "reference"],
  });
  const recipient = recipients.find((r) => r.recipient_id === recipientId);
  const corridor = corridors.items.find((c) => c.country === recipient?.country);
  const key = useIdempotencyKey(
    `${recipientId}|${purpose}|${tranches}|${amount}|${first}|${reference}`,
  );

  /** Starting amount for the chosen currency: one tuition payment, or a month of living costs each. */
  function suggest(nextPurpose: Purpose, count: number, nextRecipient: Recipient | undefined) {
    const target = corridors.items.find((c) => c.country === nextRecipient?.country);
    if (!target) return;
    const defaults = formDefaults(target);
    form.setValue(
      "amount",
      nextPurpose === "TUITION"
        ? defaults.amount
        : String(Number(defaults.sendPlanMonthly) * count),
      {
        shouldValidate: true,
      },
    );
  }

  async function onSubmit(values: Values) {
    setError(null);
    if (!recipient || !corridor) return;
    const parsed = parseMajorToMinor(values.amount, corridor.exponent);
    if (!parsed.ok) return;
    const count = Number(values.tranches);
    try {
      await post(
        "/escrows",
        {
          recipient_id: recipient.recipient_id,
          purpose: values.purpose,
          total: { amount_minor: parsed.minor, currency: corridor.currency },
          tranches: count,
          first_release: values.first,
          cadence: count > 1 ? "MONTHLY" : "ONCE",
          reference: values.reference.trim(),
        },
        { idempotencyKey: key },
      );
      form.setValue("reference", "");
      onPlanned();
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <Card aria-labelledby="escrow-plan-title" className="border-primary/40">
      <CardHeader>
        <CardTitle id="escrow-plan-title" className="text-base">
          Plan an escrow
        </CardTitle>
        <CardDescription>
          Lock money in a smart contract that pays on the dates you choose. Planning locks nothing:
          you see the schedule first, then confirm with MFA. Tuition is one payment on the due date;
          living costs are a payment every month.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <ErrorNotice error={error} />
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="recipientId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="escrow-recipient">Who gets paid</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={(v) => {
                        field.onChange(v);
                        suggest(
                          purpose,
                          Number(tranches) || 1,
                          recipients.find((r) => r.recipient_id === v),
                        );
                      }}
                    >
                      <FormControl>
                        <SelectTrigger id="escrow-recipient" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {recipients.map((r) => (
                          <SelectItem key={r.recipient_id} value={r.recipient_id}>
                            {r.label}
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
                name="purpose"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="escrow-purpose">What for</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={(v) => {
                        const next = v as Purpose;
                        const count = next === "LIVING" ? 3 : 1;
                        field.onChange(next);
                        form.setValue("tranches", String(count));
                        suggest(next, count, recipient);
                      }}
                    >
                      <FormControl>
                        <SelectTrigger id="escrow-purpose" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="TUITION">Tuition (one payment)</SelectItem>
                        <SelectItem value="LIVING">Living costs (monthly)</SelectItem>
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="amount"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Total to lock{corridor ? ` (${corridor.currency})` : ""}</FormLabel>
                    <FormControl>
                      <Input inputMode="decimal" className="font-mono" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="tranches"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Number of payments</FormLabel>
                    <FormControl>
                      <Input inputMode="numeric" className="font-mono" {...field} />
                    </FormControl>
                    <FormDescription>1 to 24. Several means one a month.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="first"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="escrow-first">
                      {Number(tranches) > 1 ? "First payment on" : "Pay on"}
                    </FormLabel>
                    <DatePicker id="escrow-first" value={field.value} onChange={field.onChange} />
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="reference"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Reference</FormLabel>
                    <FormControl>
                      <Input maxLength={70} placeholder="INV-2026-4471 / STU-883201" {...field} />
                    </FormControl>
                    <FormDescription>
                      For example the invoice number. Only a hash of it goes on the chain.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <Button
              type="submit"
              loading={form.formState.isSubmitting}
              disabled={!recipient || !amount.trim() || !reference.trim()}
            >
              Plan escrow
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
