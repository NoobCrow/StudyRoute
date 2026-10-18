"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheck } from "lucide-react";
import { useImperativeHandle, useRef, useState, type Ref } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ErrorNotice } from "@/components/app/notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Textarea } from "@/components/ui/textarea";
import { post } from "@/lib/api/client";
import type { ChecklistItem } from "@/lib/api/types";
import { sampleFilename } from "@/lib/domain/documents";

const documentSchema = z.object({
  kind: z.string().min(1, "Choose a document type."),
  filename: z
    .string()
    .trim()
    .min(1, "Enter a file name.")
    .max(120, "The file name can have at most 120 characters."),
  content: z.string().max(20000, "The text can have at most 20,000 characters."),
});
type DocumentValues = z.infer<typeof documentSchema>;

/** What the checklist's "Add mock file" button asks of the form. */
export interface AddDocumentHandle {
  prepare: (kind: string) => void;
}

/** Adds a mock document. Only text is kept, and it is data: it can never instruct the assistant. */
export function AddDocumentForm({
  kinds,
  onAdded,
  handle,
}: {
  kinds: ChecklistItem[];
  onAdded: () => void;
  handle: Ref<AddDocumentHandle>;
}) {
  const [error, setError] = useState<Error | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const form = useForm<DocumentValues>({
    resolver: zodResolver(documentSchema),
    mode: "onTouched",
    defaultValues: { kind: "offer_letter", filename: sampleFilename("offer_letter"), content: "" },
  });

  useImperativeHandle(handle, () => ({
    prepare(kind) {
      form.setValue("kind", kind, { shouldDirty: true });
      form.setValue("filename", sampleFilename(kind), { shouldValidate: true, shouldDirty: true });
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      root.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
      form.setFocus("filename");
    },
  }));

  async function onSubmit(values: DocumentValues) {
    setError(null);
    try {
      await post("/documents", {
        kind: values.kind,
        filename: values.filename.trim(),
        content_text: values.content || undefined,
      });
      form.setValue("content", "");
      toast.success("Mock document added", { description: values.filename.trim() });
      onAdded();
    } catch (e) {
      setError(e as Error);
      toast.error("The document could not be added");
    }
  }

  return (
    <div ref={root}>
      <Card aria-labelledby="upload-title">
        <CardHeader>
          <CardTitle id="upload-title" className="text-base">
            Add a mock document
          </CardTitle>
          <CardAction>
            <Badge variant="warning">Mock text only</Badge>
          </CardAction>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <ErrorNotice error={error} />
              <div className="grid items-start gap-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="kind"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="doc-kind">Document type</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger id="doc-kind" className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {kinds.map((kind) => (
                            <SelectItem key={kind.key} value={kind.key}>
                              {kind.label}
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
                  name="filename"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>File name</FormLabel>
                      <FormControl>
                        <Input maxLength={120} autoComplete="off" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <FormField
                control={form.control}
                name="content"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Text content{" "}
                      <span className="text-muted-foreground font-normal">(optional)</span>
                    </FormLabel>
                    <FormControl>
                      <Textarea rows={4} maxLength={20000} {...field} />
                    </FormControl>
                    <FormDescription className="flex items-center gap-1.5">
                      <ShieldCheck className="size-3.5 shrink-0" aria-hidden="true" />
                      Treated as data only. Text inside a document can never give the assistant an
                      instruction.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" loading={form.formState.isSubmitting}>
                Add document
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
