"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, type Resolver, useWatch } from "react-hook-form";

import { CountrySelect } from "@/components/app/country-select";
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
import {
  EMPTY_RECIPIENT,
  EXAMPLE,
  recipientBody,
  recipientSchema,
  usesIban,
  type RecipientValues,
} from "@/lib/schemas/recipient";

/** Adds a recipient. The account fields follow the destination's account scheme. */
export function RecipientForm({
  corridors,
  onCreated,
}: {
  corridors: Corridor[];
  onCreated: () => void;
}) {
  const [error, setError] = useState<Error | null>(null);
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
    mode: "onBlur",
    defaultValues: EMPTY_RECIPIENT,
  });
  const country = useWatch({ control: form.control, name: "country" });
  const ukMode = useWatch({ control: form.control, name: "ukMode" });
  const corridor = corridors.find((c) => c.country === country);
  const scheme = corridor?.account_scheme;
  const iban = usesIban(corridor, ukMode);

  async function onSubmit(values: RecipientValues) {
    setError(null);
    try {
      await post("/recipients", recipientBody(values, corridor));
      form.reset({ ...EMPTY_RECIPIENT, country: values.country });
      onCreated();
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <Card aria-labelledby="new-recipient-title">
      <CardHeader>
        <CardTitle id="new-recipient-title" className="text-base">
          Add a recipient
        </CardTitle>
        <CardDescription>
          Use synthetic details only. Never enter a real account number in the sandbox.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <ErrorNotice error={error} />
            <div className="grid gap-4 sm:grid-cols-2">
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
                      <Input maxLength={120} {...field} />
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
                  onValueChange={(v) => form.setValue("country", v)}
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
                        className="font-mono"
                        {...field}
                        onChange={(e) => field.onChange(e.target.value.toUpperCase())}
                      />
                    </FormControl>
                    <FormDescription>
                      8 or 11 characters. The country letters must match.
                    </FormDescription>
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
                    <FormLabel>Account format</FormLabel>
                    <RadioGroup
                      value={field.value}
                      onValueChange={field.onChange}
                      className="flex flex-wrap gap-6"
                    >
                      <label className="flex items-center gap-2 text-sm">
                        <RadioGroupItem value="iban" /> IBAN
                      </label>
                      <label className="flex items-center gap-2 text-sm">
                        <RadioGroupItem value="domestic" /> UK sort code and account
                      </label>
                    </RadioGroup>
                  </FormItem>
                )}
              />
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              {iban ? (
                <FormField
                  control={form.control}
                  name="iban"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>IBAN</FormLabel>
                      <FormControl>
                        <Input autoComplete="off" className="font-mono" {...field} />
                      </FormControl>
                      <FormDescription>
                        The check digits are verified (ISO 13616, mod 97).
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              ) : (
                <>
                  <FormField
                    control={form.control}
                    name="account"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Account number</FormLabel>
                        <FormControl>
                          <Input autoComplete="off" className="font-mono" {...field} />
                        </FormControl>
                        {scheme === "IBAN_OR_UK_DOMESTIC" ? (
                          <FormDescription>8 digits.</FormDescription>
                        ) : null}
                        <FormMessage />
                      </FormItem>
                    )}
                  />
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
                            <Input autoComplete="off" className="font-mono" {...field} />
                          </FormControl>
                          <FormDescription>
                            {scheme === "ABA_ACCOUNT" ? "9 digits with a checksum." : "6 digits."}
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  ) : null}
                </>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" loading={form.formState.isSubmitting}>
                Save recipient
              </Button>
              {country === "GB" ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    form.reset({
                      ...EMPTY_RECIPIENT,
                      name: EXAMPLE.name,
                      bic: EXAMPLE.bic,
                      iban: EXAMPLE.iban,
                    })
                  }
                >
                  Fill a synthetic example
                </Button>
              ) : null}
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
