import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { del, get, post } from "../api/client";
import type { Checklist, CorridorList, DocumentView } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Badge, ErrorNotice, Field, Loading, Notice, NotVerifiedBadge, PageHead } from "../components/Ui";
import { useAsync } from "../hooks";
import { formatDateTime } from "../lib/format";

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
    <section className="card" aria-labelledby="checklist-title">
      <div className="row between">
        <h2 id="checklist-title">What the bank may ask for</h2>
        <span className="row">
          {checklist.verified ? <Badge tone="ok">Verified</Badge> : <NotVerifiedBadge />}
          <Badge tone={done === checklist.items.length ? "ok" : "info"}>{done} of {checklist.items.length} ready</Badge>
        </span>
      </div>
      <ul className="stack" aria-label="Document checklist">
        {checklist.items.map((item) => (
          <li key={item.key} className="row between">
            <div>
              <span aria-hidden="true">{item.provided ? "☑" : "☐"} </span>
              <strong>{item.label}</strong>
              <span className="sr-only">{item.provided ? " (ready)" : " (missing)"}</span>
              <div className="small muted">{item.hint}</div>
            </div>
            {canWrite && !item.provided ? (
              <button type="button" className="btn small" onClick={() => onAdd(item.key)}>Add mock file</button>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="small muted">
        {checklist.indicative}
        {checklist.note ? ` ${checklist.note}` : ""}
        {checklist.source_url ? ` Source to confirm: ${checklist.source_url} (last checked ${checklist.last_checked ?? "never"}).` : ""}
      </p>
    </section>
  );
}

export function DocumentsScreen() {
  const { user } = useAuth();
  const corridors = useAsync(() => get<CorridorList>("/corridors"), []);
  const [country, setCountry] = useState("GB");
  const [purpose, setPurpose] = useState("TUITION");
  const checklist = useAsync(() => get<Checklist>(`/checklist?country=${country}&purpose=${purpose}`), [country, purpose]);
  const documents = useAsync(() => get<{ items: DocumentView[] }>("/documents"), []);
  const [kind, setKind] = useState("offer_letter");
  const [filename, setFilename] = useState("offer-letter-mock.txt");
  const [content, setContent] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const form = useRef<HTMLFormElement>(null);

  const canWrite = user?.permissions.includes("documents:write") ?? false;
  const kinds = checklist.data?.items ?? [];

  function prepare(nextKind: string) {
    setKind(nextKind);
    setFilename(`${nextKind.replaceAll("_", "-")}-mock.txt`);
    form.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/documents", { kind, filename: filename.trim(), content_text: content || undefined });
      setContent("");
      documents.reload();
      checklist.reload();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await del(`/documents/${id}`);
      documents.reload();
      checklist.reload();
    } catch (e) {
      setError(e as Error);
    }
  }

  return (
    <div className="stack">
      <PageHead title="Documents">
        A tick-off list of what your bank may ask for. Files here are mock text only: never upload a real passport or ID.
      </PageHead>
      <div className="form-grid">
        <Field label="Destination" htmlFor="d-country">
          <select id="d-country" value={country} onChange={(e) => setCountry(e.target.value)}>
            {(corridors.data?.items ?? []).map((c) => <option key={c.country} value={c.country}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="Purpose" htmlFor="d-purpose">
          <select id="d-purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            <option value="TUITION">Tuition</option>
            <option value="LIVING">Living costs</option>
          </select>
        </Field>
      </div>
      <ErrorNotice error={checklist.error ?? documents.error ?? error} />
      {checklist.loading && !checklist.data ? <Loading /> : null}
      {checklist.data ? <ChecklistCard checklist={checklist.data} canWrite={canWrite} onAdd={prepare} /> : null}

      {canWrite ? (
        <form ref={form} className="card" onSubmit={submit} aria-labelledby="upload-title">
          <h2 id="upload-title">Add a mock document</h2>
          <div className="form-grid">
            <Field label="Document type" htmlFor="doc-kind">
              <select id="doc-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
                {kinds.map((i) => <option key={i.key} value={i.key}>{i.label}</option>)}
              </select>
            </Field>
            <Field label="File name" htmlFor="doc-name">
              <input id="doc-name" value={filename} onChange={(e) => setFilename(e.target.value)} maxLength={120} />
            </Field>
          </div>
          <Field label="Text content (optional)" htmlFor="doc-text" hint="Treated as data only. Text inside a document can never give the assistant an instruction.">
            <textarea id="doc-text" value={content} onChange={(e) => setContent(e.target.value)} maxLength={20000} />
          </Field>
          <button type="submit" className="btn primary" disabled={busy || !filename.trim()}>Add document</button>
        </form>
      ) : (
        <Notice tone="info">Only the paying parent can add documents.</Notice>
      )}

      <section className="card" aria-labelledby="docs-title">
        <h2 id="docs-title">Your mock documents</h2>
        {documents.data && documents.data.items.length === 0 ? <p className="muted">Nothing added yet.</p> : null}
        <ul className="stack">
          {(documents.data?.items ?? []).map((doc) => (
            <li key={doc.document_id} className="row between">
              <div>
                <strong>{doc.filename}</strong> <Badge tone="neutral">{doc.kind.replaceAll("_", " ")}</Badge>
                <div className="small muted">{formatDateTime(doc.created_at)} - {doc.size_bytes} bytes - mock</div>
                {doc.content_preview ? <div className="small mono">{doc.content_preview}</div> : null}
              </div>
              {canWrite ? <button type="button" className="btn small" onClick={() => void remove(doc.document_id)}>Delete</button> : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
