"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CircleCheck, Circle, FileText } from "lucide-react";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { CountrySelect } from "@/components/app/country-select";
import { EmptyState } from "@/components/app/empty-state";
import { Field } from "@/components/app/field";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip, NotVerifiedBadge } from "@/components/app/status";
import { useAuth } from "@/components/providers/auth-provider";
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
import { del, post } from "@/lib/api/client";
import type { Checklist, CorridorList, DocumentView } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

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

function ChecklistCard({
  checklist,
  canWrite,
  onAdd,
}: {
  checklist: Checklist;
  canWrite: boolean;
  onAdd: (kind: string) => void;
}) {
  const done = checklist.items.filter((i) => i.provided).length;
  return (
    <Card aria-labelledby="checklist-title">
      <CardHeader>
        <CardTitle id="checklist-title" className="text-base">
          What the bank may ask for
        </CardTitle>
        <CardAction className="flex items-center gap-2">
          {checklist.verified ? <Chip tone="ok">Verified</Chip> : <NotVerifiedBadge />}
          <Chip tone={done === checklist.items.length ? "ok" : "info"}>
            {done} of {checklist.items.length} ready
          </Chip>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        <ul aria-label="Document checklist" className="divide-y rounded-lg border">
          {checklist.items.map((item) => (
            <li key={item.key} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="flex gap-3">
                {item.provided ? (
                  <CircleCheck className="text-primary mt-0.5 size-5 shrink-0" aria-hidden="true" />
                ) : (
                  <Circle
                    className="text-muted-foreground mt-0.5 size-5 shrink-0"
                    aria-hidden="true"
                  />
                )}
                <div>
                  <strong className={cn("font-medium", item.provided && "text-muted-foreground")}>
                    {item.label}
                  </strong>
                  <span className="sr-only">{item.provided ? " (ready)" : " (missing)"}</span>
                  <div className="text-muted-foreground text-xs">{item.hint}</div>
                </div>
              </div>
              {canWrite && !item.provided ? (
                <Button type="button" variant="outline" size="sm" onClick={() => onAdd(item.key)}>
                  Add mock file
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
        <p className="text-muted-foreground text-xs">
          {checklist.indicative}
          {checklist.note ? ` ${checklist.note}` : ""}
          {checklist.source_url
            ? ` Source to confirm: ${checklist.source_url} (last checked ${checklist.last_checked ?? "never"}).`
            : ""}
        </p>
      </CardContent>
    </Card>
  );
}

export function DocumentsScreen() {
  const { user } = useAuth();
  const corridors = useApi<CorridorList>("/corridors");
  const [country, setCountry] = useState("GB");
  const [purpose, setPurpose] = useState("TUITION");
  const checklist = useApi<Checklist>(`/checklist?country=${country}&purpose=${purpose}`);
  const documents = useApi<{ items: DocumentView[] }>("/documents");
  const [error, setError] = useState<Error | null>(null);
  const formRef = useRef<HTMLDivElement>(null);
  const form = useForm<DocumentValues>({
    resolver: zodResolver(documentSchema),
    mode: "onBlur",
    defaultValues: { kind: "offer_letter", filename: "offer-letter-mock.txt", content: "" },
  });

  const canWrite = user?.permissions.includes("documents:write") ?? false;
  const kinds = checklist.data?.items ?? [];

  function prepare(nextKind: string) {
    form.setValue("kind", nextKind);
    form.setValue("filename", `${nextKind.replaceAll("_", "-")}-mock.txt`, {
      shouldValidate: true,
    });
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function onSubmit(values: DocumentValues) {
    setError(null);
    try {
      await post("/documents", {
        kind: values.kind,
        filename: values.filename.trim(),
        content_text: values.content || undefined,
      });
      form.setValue("content", "");
      documents.reload();
      checklist.reload();
      toast.success("Mock document added");
    } catch (e) {
      setError(e as Error);
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await del(`/documents/${id}`);
      documents.reload();
      checklist.reload();
      toast.success("Document deleted");
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <div className="space-y-6">
      <PageHead title="Documents">
        A tick-off list of what your bank may ask for. Files here are mock text only: never upload a
        real passport or ID.
      </PageHead>
      <div className="grid gap-4 sm:max-w-xl sm:grid-cols-2">
        <Field label="Destination" htmlFor="d-country">
          <CountrySelect
            id="d-country"
            corridors={corridors.data?.items ?? []}
            value={country}
            onValueChange={setCountry}
          />
        </Field>
        <Field label="Purpose" htmlFor="d-purpose">
          <Select value={purpose} onValueChange={setPurpose}>
            <SelectTrigger id="d-purpose" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="TUITION">Tuition</SelectItem>
              <SelectItem value="LIVING">Living costs</SelectItem>
            </SelectContent>
          </Select>
        </Field>
      </div>
      <ErrorNotice error={checklist.error ?? documents.error ?? error} onRetry={checklist.reload} />
      {checklist.loading && !checklist.data ? (
        <CardSkeleton lines={4} label="Loading the checklist" />
      ) : null}
      {checklist.data ? (
        <ChecklistCard checklist={checklist.data} canWrite={canWrite} onAdd={prepare} />
      ) : null}

      {canWrite ? (
        <div ref={formRef}>
          <Card aria-labelledby="upload-title">
            <CardHeader>
              <CardTitle id="upload-title" className="text-base">
                Add a mock document
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Form {...form}>
                <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
                  <div className="grid gap-4 sm:grid-cols-2">
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
                              {kinds.map((i) => (
                                <SelectItem key={i.key} value={i.key}>
                                  {i.label}
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
                            <Input maxLength={120} {...field} />
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
                        <FormLabel>Text content (optional)</FormLabel>
                        <FormControl>
                          <Textarea rows={4} maxLength={20000} {...field} />
                        </FormControl>
                        <FormDescription>
                          Treated as data only. Text inside a document can never give the assistant
                          an instruction.
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
      ) : (
        <Notice tone="info">Only the paying parent can add documents.</Notice>
      )}

      <Card aria-labelledby="docs-title">
        <CardHeader>
          <CardTitle id="docs-title" className="text-base">
            Your mock documents
          </CardTitle>
        </CardHeader>
        <CardContent>
          {documents.data && documents.data.items.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="Nothing added yet."
              description="Add a mock file from the checklist above."
            />
          ) : null}
          <ul className="space-y-3">
            {(documents.data?.items ?? []).map((doc) => (
              <li
                key={doc.document_id}
                className="flex items-start justify-between gap-3 rounded-lg border px-4 py-3"
              >
                <div className="min-w-0">
                  <strong className="font-medium">{doc.filename}</strong>{" "}
                  <Chip tone="neutral">{doc.kind.replaceAll("_", " ")}</Chip>
                  <div className="text-muted-foreground text-xs">
                    {formatDateTime(doc.created_at)} - {doc.size_bytes} bytes - mock
                  </div>
                  {doc.content_preview ? (
                    <div className="mt-1 font-mono text-xs break-words">{doc.content_preview}</div>
                  ) : null}
                </div>
                {canWrite ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void remove(doc.document_id)}
                  >
                    Delete
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
