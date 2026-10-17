"use client";

import { FileText } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { CountrySelect } from "@/components/app/country-select";
import { EmptyState } from "@/components/app/empty-state";
import { Field } from "@/components/app/field";
import { ErrorNotice, Notice } from "@/components/app/notice";
import { PageHead } from "@/components/app/page-head";
import { CardSkeleton } from "@/components/app/skeletons";
import { Chip } from "@/components/app/status";
import { AddDocumentForm, type AddDocumentHandle } from "@/components/documents/add-document-form";
import { ChecklistCard } from "@/components/documents/checklist-card";
import { useAuth } from "@/components/providers/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { del } from "@/lib/api/client";
import type { Checklist, CorridorList, DocumentView } from "@/lib/api/types";
import { useApi } from "@/lib/api/use-api";
import { documentKindLabel, fileCount } from "@/lib/domain/documents";
import { formatDateTime } from "@/lib/format";

export function DocumentsScreen() {
  const { user } = useAuth();
  const corridors = useApi<CorridorList>("/corridors");
  const [country, setCountry] = useState("GB");
  const [purpose, setPurpose] = useState("TUITION");
  const checklist = useApi<Checklist>(`/checklist?country=${country}&purpose=${purpose}`);
  const documents = useApi<{ items: DocumentView[] }>("/documents");
  const [error, setError] = useState<Error | null>(null);
  const form = useRef<AddDocumentHandle>(null);

  const canWrite = user?.permissions.includes("documents:write") ?? false;
  const files = documents.data?.items ?? [];

  function changed() {
    documents.reload();
    checklist.reload();
  }

  async function remove(id: string) {
    setError(null);
    try {
      await del(`/documents/${id}`);
      changed();
      toast.success("Document deleted");
    } catch (e) {
      setError(e as Error);
      toast.error("The document could not be deleted");
    }
  }

  return (
    <div className="space-y-6">
      <PageHead title="Documents">
        A tick-off list of what your bank may ask for. Files here are mock text only: never upload a
        real passport or ID.
      </PageHead>
      <div className="grid gap-3 sm:grid-cols-[repeat(2,minmax(0,14.5rem))]">
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
      <ErrorNotice
        error={checklist.error ?? documents.error ?? error}
        onRetry={() => {
          checklist.reload();
          documents.reload();
        }}
      />
      {checklist.loading && !checklist.data ? (
        <CardSkeleton lines={4} label="Loading the checklist" />
      ) : null}
      {checklist.data ? (
        <ChecklistCard
          checklist={checklist.data}
          canWrite={canWrite}
          onAdd={(kind) => form.current?.prepare(kind)}
        />
      ) : null}

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {canWrite ? (
          <AddDocumentForm handle={form} kinds={checklist.data?.items ?? []} onAdded={changed} />
        ) : (
          <Notice tone="info">Only the paying parent can add documents.</Notice>
        )}

        <Card aria-labelledby="docs-title">
          <CardHeader>
            <CardTitle id="docs-title" className="text-base">
              Your mock documents
            </CardTitle>
            <CardAction>
              <Badge variant="muted">{fileCount(files.length)}</Badge>
            </CardAction>
          </CardHeader>
          <CardContent>
            {documents.data && files.length === 0 ? (
              <EmptyState icon={FileText} title="Nothing added yet." />
            ) : null}
            <ul className="space-y-3">
              {files.map((doc) => (
                <li
                  key={doc.document_id}
                  className="flex items-start justify-between gap-3 rounded-lg border px-4 py-3"
                >
                  <div className="min-w-0">
                    {/* Plain text: a file name or its text is never treated as markup. */}
                    <strong className="font-medium [overflow-wrap:anywhere]">
                      {doc.filename}
                    </strong>{" "}
                    <Chip tone="neutral">{documentKindLabel(doc.kind)}</Chip>
                    <div className="text-muted-foreground text-xs">
                      {formatDateTime(doc.created_at)} - {doc.size_bytes} bytes - mock
                    </div>
                    {doc.content_preview ? (
                      <div className="mt-1 font-mono text-xs [overflow-wrap:anywhere]">
                        {doc.content_preview}
                      </div>
                    ) : null}
                  </div>
                  {canWrite ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      aria-label={`Delete ${doc.filename}`}
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
    </div>
  );
}
