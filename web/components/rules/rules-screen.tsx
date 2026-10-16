"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip, NotVerifiedBadge } from "@/components/app/status";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { put } from "@/lib/api/client";
import type { RuleView } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";

interface RulesResponse {
  rules: RuleView[];
  unverified_count: number;
  disclaimer: string;
}

function compact(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 70 ? `${text.slice(0, 67)}...` : text;
}

const editSchema = z
  .object({
    value: z.string().superRefine((text, ctx) => {
      try {
        JSON.parse(text);
      } catch {
        ctx.addIssue({
          code: "custom",
          message: 'The value must be valid JSON, for example 300, true or "15:00".',
        });
      }
    }),
    source: z.string(),
    verified: z.boolean(),
    reason: z.string().trim().min(3, "Say why you are changing it.").max(160),
  })
  .refine((v) => !v.verified || v.source.trim() !== "", {
    path: ["source"],
    message: "A verified rule needs the source URL it was checked against.",
  });
type EditValues = z.infer<typeof editSchema>;

function EditDialog({
  rule,
  onDone,
  onCancel,
}: {
  rule: RuleView;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [error, setError] = useState<Error | null>(null);
  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    mode: "onBlur",
    defaultValues: {
      value: JSON.stringify(rule.value, null, 2),
      source: rule.source_url ?? "",
      verified: rule.verified,
      reason: "",
    },
  });

  async function onSubmit(values: EditValues) {
    setError(null);
    try {
      await put("/config/rules", {
        key: rule.key,
        value: JSON.parse(values.value) as unknown,
        source_url: values.source.trim() || null,
        verified: values.verified,
        reason: values.reason.trim(),
      });
      toast.success("Rule saved", { description: "The change was written to the audit log." });
      onDone();
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="sm:max-w-xl">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <DialogHeader>
              <DialogTitle>
                Change <code className="font-mono text-base">{rule.key}</code>
              </DialogTitle>
              <DialogDescription>
                The change is written to the audit log with your name and the reason.
              </DialogDescription>
            </DialogHeader>
            <ErrorNotice error={error} />
            <FormField
              control={form.control}
              name="value"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Value (JSON)</FormLabel>
                  <FormControl>
                    <Textarea
                      rows={5}
                      spellCheck={false}
                      className="font-mono text-xs"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="source"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Source URL</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="verified"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center gap-2">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={(v) => field.onChange(v === true)}
                    />
                  </FormControl>
                  <Label className="font-normal">Checked against the official source</Label>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="reason"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Why are you changing it?</FormLabel>
                  <FormControl>
                    <Input maxLength={160} {...field} />
                  </FormControl>
                  <FormDescription>Required: it goes into the audit log.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onCancel}>
                Cancel
              </Button>
              <Button type="submit" loading={form.formState.isSubmitting}>
                Save change
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

export function RulesScreen() {
  const { user } = useAuth();
  const rules = useApi<RulesResponse>("/config/rules");
  const [onlyUnverified, setOnlyUnverified] = useState(false);
  const [editing, setEditing] = useState<RuleView | null>(null);
  const canEdit = user?.permissions.includes("config:write") ?? false;
  const all = rules.data?.rules ?? [];
  const shown = onlyUnverified ? all.filter((r) => !r.verified) : all;

  return (
    <div className="space-y-6">
      <PageHead title="Rules and limits">
        Every limit, fee assumption, calendar and checklist lives in configuration, never in code.
        Anything not checked against an official source is marked.
      </PageHead>
      {rules.data ? (
        <Notice
          tone={rules.data.unverified_count > 0 ? "warn" : "ok"}
          title={`${rules.data.unverified_count} rules are not verified`}
        >
          {rules.data.disclaimer}
        </Notice>
      ) : null}
      <ErrorNotice error={rules.error} onRetry={rules.reload} />
      <div className="flex items-center gap-2">
        <Checkbox
          id="only-unverified"
          checked={onlyUnverified}
          onCheckedChange={(v) => setOnlyUnverified(v === true)}
        />
        <Label htmlFor="only-unverified" className="font-normal">
          Show only rules that are not verified
        </Label>
      </div>
      {rules.loading && !rules.data ? <CardSkeleton lines={5} label="Loading rules" /> : null}
      {shown.length > 0 ? (
        <div
          className="bg-card overflow-x-auto rounded-xl border"
          tabIndex={0}
          role="region"
          aria-label="Rules table"
        >
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Rule</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Source</TableHead>
                {canEdit ? (
                  <TableHead>
                    <span className="sr-only">Edit</span>
                  </TableHead>
                ) : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((r) => (
                <TableRow key={r.key}>
                  <TableCell className="align-top whitespace-normal">
                    <code className="font-mono text-xs">{r.key}</code>
                    <div className="text-muted-foreground text-xs">{r.kind.replace("_", " ")}</div>
                  </TableCell>
                  <TableCell className="align-top font-mono text-xs whitespace-normal">
                    {compact(r.value)}
                  </TableCell>
                  <TableCell className="align-top whitespace-normal">
                    {r.verified ? <Chip tone="ok">Verified</Chip> : <NotVerifiedBadge />}
                    {r.indicative ? <div className="mt-1 text-xs">{r.indicative}</div> : null}
                  </TableCell>
                  <TableCell className="max-w-64 align-top text-xs whitespace-normal">
                    <span className="break-all">{r.source_url ?? "-"}</span>
                    {r.last_checked ? (
                      <div className="text-muted-foreground">checked {r.last_checked}</div>
                    ) : null}
                    {r.note ? <div className="text-muted-foreground">{r.note}</div> : null}
                  </TableCell>
                  {canEdit ? (
                    <TableCell className="align-top">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setEditing(r)}
                      >
                        Edit
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {editing ? (
        <EditDialog
          rule={editing}
          onCancel={() => setEditing(null)}
          onDone={() => {
            setEditing(null);
            rules.reload();
          }}
        />
      ) : null}
    </div>
  );
}
