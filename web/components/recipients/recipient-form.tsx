"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Check } from "lucide-react";
import { useState } from "react";
import { useForm, type Resolver, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { CountrySelect } from "@/components/app/country-select";
import { ErrorNotice } from "@/components/app/notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { post } from "@/lib/api/client";
import type { Corridor } from "@/lib/api/types";
import { BIC_HELP, IBAN_VALID, validateIban } from "@/lib/domain/recipient-validation";
import {
  EMPTY_RECIPIENT,
  EXAMPLE_RECIPIENT,
  recipientBody,
  recipientSchema,
  usesIban,
  type RecipientValues,
  type UkMode,
} from "@/lib/schemas/recipient";
import { cn } from "@/lib/utils";

const FORMATS: { value: UkMode; title: string; text: string }[] = [
  { value: "iban", title: "IBAN", text: "One number that holds the bank and the account." },
  {
    value: "domestic",
    title: "UK sort code and account",
    text: "A 6-digit sort code and an 8-digit account number.",
  },
];

/** Adds a recipient. The account fields follow the destination's account scheme. */
export function RecipientForm({
  corridors,
  onCreated,
}: {
  corridors: Corridor[];
  onCreated: () => void;
}) {
  const [error, setError] = useState<Error | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [institutionId, setInstitutionId] = useState("");
  const resolver: Resolver<RecipientValues> = (values, context, options) => {
    const corridor = corridors.find((c) => c.country === values.country);
    return zodResolver(recipientSchema(corridor, values.ukMode))(
      values,
      context,
      options,
    ) as ReturnType<Resolver<RecipientValues>>;
  };
  const form = useForm<RecipientValues>({
    resolver,
    mode: "onTouched", // errors appear after the first blur, then follow every change
    defaultValues: EMPTY_RECIPIENT,
  });
  // Read unconditionally: React Hook Form only tracks a state value that is read on the first render.
  const { isSubmitting, isValid } = form.formState;
  const country = useWatch({ control: form.control, name: "country" });
  const ukMode = useWatch({ control: form.control, name: "ukMode" });
  const ibanText = useWatch({ control: form.control, name: "iban" });
  const corridor = corridors.find((c) => c.country === country);
  const scheme = corridor?.account_scheme;
  const iban = usesIban(corridor, ukMode);
  const ibanOk = iban && ibanText.trim() !== "" && validateIban(ibanText, country).ok;

  async function onSubmit(values: RecipientValues) {
    setError(null);
    try {
      await post("/recipients", {
        ...recipientBody(values, corridor),
        ...(institutionId ? { institution_id: institutionId } : {}),
      });
      setInstitutionId("");
      form.reset({ ...EMPTY_RECIPIENT, country: values.country });
      const name = values.name.trim();
      setSaved(`${name} was saved. It is not allowlisted yet.`);
      toast.success("Recipient saved", { description: `${name} is not allowlisted yet.` });
      onCreated();
    } catch (e) {
      setError(e as Error);
      toast.error("The recipient could not be saved");
    }
  }

  function fillExample() {
    setSaved(null);
    form.reset(EXAMPLE_RECIPIENT);
    void form.trigger();
  }

  return (
    <Card id="add" aria-labelledby="new-recipient-title" className="scroll-mt-24">
      <CardHeader>
        <CardTitle id="new-recipient-title" className="text-base">
          Add a recipient
        </CardTitle>
        <CardDescription>
          Use synthetic details only. Never enter a real account number in the sandbox.
        </CardDescription>
        <CardAction>
          <Badge variant="warning">Synthetic data only</Badge>
        </CardAction>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            onChange={() => setSaved(null)}
            className="space-y-5"
            noValidate
          >
            <ErrorNotice error={error} />
            <FormItem>
              <FormLabel htmlFor="r-institution">University payment-route policy</FormLabel>
              <select
                id="r-institution"
                value={institutionId}
                onChange={(event) => setInstitutionId(event.target.value)}
                className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
              >
                <option value="">Not in the reviewed catalogue — unverified, sandbox only</option>
                <option value="gb-manchester-metropolitan">
                  Manchester Metropolitan University — Flywire required for tuition
                </option>
              </select>
              <FormDescription>
                Declaration is not identity verification. The server blocks direct-bank tuition
                quotes and payments for the configured university, even after renaming. No Flywire
                integration or live bank quote is provided.
              </FormDescription>
            </FormItem>
            <div className="grid items-start gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <FormField
                control={form.control}
                name="type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="r-type">Type</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger id="r-type" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="UNIVERSITY">University</SelectItem>
                        <SelectItem value="STUDENT">Student</SelectItem>
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input maxLength={140} autoComplete="off" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormItem>
                <FormLabel htmlFor="r-country">Country</FormLabel>
                <CountrySelect
                  id="r-country"
                  corridors={corridors}
                  value={country}
                  onValueChange={(value) => {
                    form.setValue("country", value, { shouldDirty: true, shouldValidate: true });
                    form.setValue("ukMode", "iban");
                  }}
                />
              </FormItem>
              <FormField
                control={form.control}
                name="bic"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Bank BIC (SWIFT code)</FormLabel>
                    <FormControl>
                      <Input
                        maxLength={11}
                        autoCapitalize="characters"
                        autoComplete="off"
                        className="font-mono uppercase"
                        {...field}
                        onChange={(e) => field.onChange(e.target.value.toUpperCase())}
                      />
                    </FormControl>
                    <FormDescription>{BIC_HELP}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            {scheme === "IBAN_OR_UK_DOMESTIC" ? (
              <FormField
                control={form.control}
                name="ukMode"
                render={({ field }) => (
                  <FormItem>
                    <fieldset className="space-y-2">
                      <legend className="text-sm leading-none font-medium">Account format</legend>
                      <RadioGroup
                        value={field.value}
                        onValueChange={field.onChange}
                        aria-label="Account format"
                        className="grid gap-3 sm:grid-cols-2"
                      >
                        {FORMATS.map((format) => (
                          <label
                            key={format.value}
                            htmlFor={`format-${format.value}`}
                            className={cn(
                              "has-[:focus-visible]:ring-ring/50 flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 transition-colors has-[:focus-visible]:ring-[3px]",
                              field.value === format.value
                                ? "border-primary/40 bg-success-soft/60"
                                : "hover:bg-muted/50",
                            )}
                          >
                            <RadioGroupItem
                              id={`format-${format.value}`}
                              value={format.value}
                              className="mt-0.5"
                            />
                            <span className="space-y-0.5">
                              <span className="block text-sm font-semibold">{format.title}</span>
                              <span className="text-muted-foreground block text-[13px]">
                                {format.text}
                              </span>
                            </span>
                          </label>
                        ))}
                      </RadioGroup>
                    </fieldset>
                  </FormItem>
                )}
              />
            ) : null}
            {iban ? (
              <FormField
                control={form.control}
                name="iban"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>IBAN</FormLabel>
                    <FormControl>
                      <Input
                        autoComplete="off"
                        spellCheck={false}
                        className="font-mono"
                        {...field}
                      />
                    </FormControl>
                    {ibanOk ? (
                      <p className="text-success-soft-foreground flex items-center gap-1.5 text-[13px]">
                        <Check className="size-3.5" aria-hidden="true" />
                        {IBAN_VALID}
                      </p>
                    ) : null}
                    <FormMessage />
                  </FormItem>
                )}
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {scheme === "IBAN_OR_UK_DOMESTIC" || scheme === "ABA_ACCOUNT" ? (
                  <FormField
                    control={form.control}
                    name="routing"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          {scheme === "ABA_ACCOUNT" ? "ABA routing number" : "Sort code"}
                        </FormLabel>
                        <FormControl>
                          <Input
                            inputMode="numeric"
                            autoComplete="off"
                            className="font-mono"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          {scheme === "ABA_ACCOUNT" ? "9 digits with a checksum." : "6 digits."}
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                ) : null}
                <FormField
                  control={form.control}
                  name="account"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Account number</FormLabel>
                      <FormControl>
                        <Input
                          inputMode="numeric"
                          autoComplete="off"
                          className="font-mono"
                          {...field}
                        />
                      </FormControl>
                      {scheme === "IBAN_OR_UK_DOMESTIC" ? (
                        <FormDescription>8 digits.</FormDescription>
                      ) : null}
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" loading={isSubmitting} disabled={!isValid}>
                Save recipient
              </Button>
              <Button type="button" variant="ghost" onClick={fillExample}>
                Fill a synthetic example
              </Button>
              <p role="status" className="text-muted-foreground text-sm">
                {saved}
              </p>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
