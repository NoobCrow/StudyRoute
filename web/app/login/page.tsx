"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { ErrorNotice, Notice } from "@/components/app/notice";
import { BrandMark } from "@/components/layout/brand-mark";
import { ThemeMenu } from "@/components/layout/theme-menu";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { loadHealth } from "@/lib/api/health";
import type { Health } from "@/lib/api/types";
import { signInSchema, type SignInValues } from "@/lib/schemas/auth";

export default function LoginPage() {
  const { user, ready, login } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<Error | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const form = useForm<SignInValues>({
    resolver: zodResolver(signInSchema),
    mode: "onBlur",
    defaultValues: { email: "", password: "" },
  });

  useEffect(() => {
    loadHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (ready && user) router.replace("/");
  }, [ready, user, router]);

  async function onSubmit(values: SignInValues) {
    setError(null);
    try {
      await login(values.email, values.password);
      router.replace("/");
    } catch (e) {
      setError(e as Error);
    }
  }

  const demo = health?.demo;
  return (
    <main className="mx-auto w-full max-w-4xl space-y-6 px-4 py-8 md:px-8">
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="bg-primary/15 animate-float absolute -top-24 -right-24 size-96 rounded-full blur-3xl" />
        <div className="bg-chart-2/15 animate-float absolute bottom-0 -left-24 size-96 rounded-full blur-3xl [animation-delay:-3s]" />
      </div>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2.5 text-base font-semibold tracking-tight">
          <BrandMark className="size-8" />
          StudyRoute
        </span>
        <ThemeMenu />
      </div>
      <div className="stagger grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <p className="text-primary text-xs font-medium tracking-wide uppercase">
              Made for families in Bangladesh
            </p>
            <h1 id="signin-title" className="text-[28px] tracking-[-0.02em]">
              Sign in to StudyRoute
            </h1>
            <CardDescription>
              An assistant for paying tuition and living costs abroad from Bangladesh. The engine
              calculates, the AI explains, a human approves, and every step is logged.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit(onSubmit)}
                className="space-y-4"
                aria-labelledby="signin-title"
                noValidate
              >
                <ErrorNotice error={error} />
                <FormField
                  control={form.control}
                  name="email"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Email</FormLabel>
                      <FormControl>
                        <Input type="email" autoComplete="username" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Password</FormLabel>
                      <FormControl>
                        <Input type="password" autoComplete="current-password" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <Button type="submit" loading={form.formState.isSubmitting} className="w-full">
                  Sign in
                </Button>
              </form>
            </Form>
          </CardContent>
        </Card>
        <Card aria-label="Sandbox demo accounts">
          <CardHeader>
            <CardTitle>Try the sandbox</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Notice tone="info">
              Every account, rate, fee and provider here is synthetic. No real money moves and no
              real bank is contacted.
            </Notice>
            {demo ? (
              <>
                <p className="text-sm">
                  Demo accounts. Password <code className="font-mono">{demo.password}</code>, MFA
                  code <code className="font-mono">{demo.mfa_code}</code>.
                </p>
                <ul className="flex flex-wrap gap-2">
                  {demo.accounts.map((account) => (
                    <li key={account}>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          form.setValue("email", account, { shouldValidate: true });
                          form.setValue("password", demo.password, { shouldValidate: true });
                        }}
                      >
                        {account}
                      </Button>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="text-muted-foreground text-sm">Ask the team for a demo account.</p>
            )}
            <p className="text-muted-foreground text-xs">
              AI mode:{" "}
              {health
                ? health.ai_mode === "template"
                  ? "template mode (no model key set)"
                  : health.ai_mode
                : "checking"}
              .
            </p>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
