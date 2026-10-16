"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

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
import type {
  BankAccountView,
  BankNetwork,
  BankTransfer,
  Beneficiary,
  ChargeCode,
} from "@/lib/api/types";
import { parseMajorToMinor } from "@/lib/money";
import { moneyText } from "@/lib/schemas/money";

const CHARGE_LABEL: Record<ChargeCode, string> = {
  OUR: "OUR: I pay every fee",
  SHA: "SHA: fees are shared",
  BEN: "BEN: the beneficiary pays",
};
const DEFAULT = "__default__";

/** Which destinations make sense for a source: same country at home, or abroad from Bangladesh. */
function routeFits(source: BankAccountView, dest: Beneficiary): boolean {
  if (dest.id === source.id) return false;
  if (source.currency === "BDT") return true;
  return dest.currency === source.currency && dest.country === source.country;
}

const planSchema = z.object({
  sourceId: z.string().min(1),
  destId: z.string().min(1, "Choose who gets the money."),
  amount: moneyText("Amount", () => 2),
  rail: z.string(),
  charge: z.string(),
  reference: z.string().max(140),
});
type PlanValues = z.infer<typeof planSchema>;

interface Props {
  accounts: BankAccountView[];
  beneficiaries: Beneficiary[];
  network: BankNetwork;
  onPlanned: (transfer: BankTransfer) => void;
}

export function PlanForm({ accounts, beneficiaries, network, onPlanned }: Props) {
  const [error, setError] = useState<Error | null>(null);
  const form = useForm<PlanValues>({
    resolver: zodResolver(planSchema),
    mode: "onBlur",
    defaultValues: {
      sourceId: accounts[0]?.id ?? "",
      destId: "",
      amount: "",
      rail: "",
      charge: "",
      reference: "Sandbox transfer",
    },
  });
  const [sourceId, destId, amount, rail, charge, reference] = useWatch({
    control: form.control,
    name: ["sourceId", "destId", "amount", "rail", "charge", "reference"],
  });

  const source = accounts.find((a) => a.id === sourceId);
  const choices = useMemo(
    () => (source ? beneficiaries.filter((b) => routeFits(source, b)) : []),
    [source, beneficiaries],
  );
  const dest = choices.find((b) => b.id === destId);
  const international = source?.currency === "BDT" && dest !== undefined && dest.currency !== "BDT";
  const sameBank =
    source !== undefined && dest !== undefined && source.bank_code === dest.bank_code;
  const rails = source ? (network.directory?.rails[source.currency] ?? []) : [];
  const key = useIdempotencyKey(`${sourceId}|${destId}|${amount}|${rail}|${charge}|${reference}`);

  async function onSubmit(values: PlanValues) {
    setError(null);
    if (!source || !dest) return;
    const parsed = parseMajorToMinor(values.amount);
    if (!parsed.ok) return;
    try {
      const body: Record<string, unknown> = {
        source: source.id,
        destination: dest.id,
        amount: { amount_minor: parsed.minor, currency: dest.currency },
        reference: values.reference.trim() || "Sandbox transfer",
      };
      if (international && values.charge) body.charge_code = values.charge;
      if (!international && !sameBank && values.rail) body.rail = values.rail;
      onPlanned(await post<BankTransfer>("/bank/transfers", body, { idempotencyKey: key }));
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <Card aria-labelledby="plan-title" className="border-primary/40">
      <CardHeader>
        <CardTitle id="plan-title" className="text-base">
          Plan a transfer
        </CardTitle>
        <CardDescription>
          Planning moves no money. You will see the fees and every hop first, then confirm with MFA.
          Pick a Bangladesh account and a UK account to see an international transfer, or two
          Bangladesh accounts to see a national one.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <ErrorNotice error={error} />
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="sourceId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="bank-source">From account</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={(v) => {
                        field.onChange(v);
                        form.setValue("destId", "");
                      }}
                    >
                      <FormControl>
                        <SelectTrigger id="bank-source" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {accounts.map((a) => (
                          <SelectItem key={a.id} value={a.id}>
                            {a.label} · {a.bank_name} · {a.balance.formatted}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="destId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="bank-dest">To account</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger id="bank-dest" className="w-full">
                          <SelectValue placeholder="Choose who gets the money" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {choices.map((b) => (
                          <SelectItem key={b.id} value={b.id}>
                            {b.holder} · {b.bank_name} · {b.currency}
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
                name="amount"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {dest ? `Amount the beneficiary receives (${dest.currency})` : "Amount"}
                    </FormLabel>
                    <FormControl>
                      <Input
                        inputMode="decimal"
                        placeholder="1000.00"
                        className="font-mono"
                        {...field}
                      />
                    </FormControl>
                    {international ? (
                      <FormDescription>
                        Fees are added to what you pay with OUR, or taken from the amount with SHA
                        and BEN.
                      </FormDescription>
                    ) : null}
                    <FormMessage />
                  </FormItem>
                )}
              />
              {international ? (
                <FormField
                  control={form.control}
                  name="charge"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="bank-charge">Who pays the fees</FormLabel>
                      <Select
                        value={field.value || DEFAULT}
                        onValueChange={(v) => field.onChange(v === DEFAULT ? "" : v)}
                      >
                        <FormControl>
                          <SelectTrigger id="bank-charge" className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value={DEFAULT}>Bank default</SelectItem>
                          {(Object.keys(CHARGE_LABEL) as ChargeCode[]).map((code) => (
                            <SelectItem key={code} value={code}>
                              {CHARGE_LABEL[code]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        Check the university&apos;s payment instructions. Indicative. Confirm with
                        your AD bank.
                      </FormDescription>
                    </FormItem>
                  )}
                />
              ) : dest && !sameBank ? (
                <FormField
                  control={form.control}
                  name="rail"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="bank-rail">Way of sending</FormLabel>
                      <Select
                        value={field.value || DEFAULT}
                        onValueChange={(v) => field.onChange(v === DEFAULT ? "" : v)}
                      >
                        <FormControl>
                          <SelectTrigger id="bank-rail" className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value={DEFAULT}>Cheapest that accepts the amount</SelectItem>
                          {rails.map((r) => (
                            <SelectItem key={r.code} value={r.code}>
                              {r.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </FormItem>
                  )}
                />
              ) : null}
              <FormField
                control={form.control}
                name="reference"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Reference</FormLabel>
                    <FormControl>
                      <Input maxLength={140} {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>
            <Button
              type="submit"
              loading={form.formState.isSubmitting}
              disabled={!source || !dest || !amount.trim()}
            >
              Plan transfer
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
