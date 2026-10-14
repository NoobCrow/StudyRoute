import { useCallback, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { post } from "../api/client";
import type { ChatAction, ChatResponse } from "../api/types";
import { useCurrentChatScope } from "../chatContext";
import { TaskView } from "./PlanCard";
import { Badge, ErrorNotice } from "./Ui";

interface Turn { id: number; role: "me" | "bot"; text: string; reply?: ChatResponse }

const SUGGESTIONS = [
  "I need to pay GBP 10,000 tuition by 28 October",
  "How often should I send GBP 800 a month for 9 months?",
  "Why is Provider B cheaper than A?",
  "What do OUR, SHA and BEN mean?",
  "What documents do I need?",
  "What is the daily limit?",
];

function actionLink(action: ChatAction, paymentId?: string): { to: string; label: string } {
  if (action.tool === "create_draft") {
    const { quote_id: quote, provider_id: provider } = action.args;
    return { to: `/compare?quote=${quote ?? ""}&provider=${provider ?? ""}`, label: "Review and confirm the draft" };
  }
  return { to: `/payments/${action.args.payment_id ?? paymentId ?? ""}`, label: "Open the payment to request approval" };
}

function GuardNote({ reply }: { reply: ChatResponse }) {
  const { status, failure, flags } = reply.guard;
  if (status === "passed" && flags.length === 0) return null;
  const text: Record<string, string> = {
    policy_blocked: "Blocked by the safety check. Nothing was changed.",
    template_fallback: `A model reply was discarded (${failure ?? "guard"}). This is the engine's template answer.`,
    llm_unavailable: "The model was unavailable. This is the engine's template answer.",
  };
  return (
    <p className="small">
      <Badge tone={status === "passed" ? "info" : "warn"}>Guard: {status.replace("_", " ")}</Badge>{" "}
      {text[status] ?? ""} {flags.length ? `Flags: ${flags.join(", ")}.` : ""}
    </p>
  );
}

function Details({ reply, paymentId }: { reply: ChatResponse; paymentId?: string }) {
  return (
    <>
      <GuardNote reply={reply} />
      {reply.facts.length > 0 ? (
        <details>
          <summary>Facts used ({reply.facts.length})</summary>
          <ul className="small">
            {reply.facts.map((fact) => (
              <li key={fact.id}><code>{fact.id}</code> {fact.label}: <strong>{fact.value}</strong></li>
            ))}
          </ul>
        </details>
      ) : null}
      {(reply.task?.kind === "payment_plan" && reply.task.status === "ready" ? [] : reply.proposed_actions).map((action) => {
        const link = actionLink(action, paymentId);
        return (
          <p key={`${action.tool}-${link.to}`} className="small">
            <Badge tone="info">Proposal only</Badge> {action.tool === "create_draft" ? "Create a draft" : "Request approval"}.{" "}
            <Link to={link.to}>{link.label}</Link>. A human must confirm; approval stays with you.
          </p>
        );
      })}
      <details>
        <summary>Debug: what the model sees (masked)</summary>
        <pre>{reply.debug.masked_prompt}</pre>
      </details>
    </>
  );
}

export function ChatPanel() {
  const scope = useCurrentChatScope();
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [mode, setMode] = useState<ChatResponse | null>(null);
  const [planQuote, setPlanQuote] = useState<string | null>(null);
  const counter = useRef(0);
  const newest = useCallback((node: HTMLDivElement | null) => {
    node?.scrollIntoView?.({ block: "start" });
  }, []);

  async function ask(message: string) {
    const clean = message.trim();
    if (!clean || busy) return;
    setText("");
    setError(null);
    setBusy(true);
    setTurns((t) => [...t, { id: ++counter.current, role: "me", text: clean }]);
    try {
      const context = { quote_id: scope.quoteId ?? planQuote, payment_id: scope.paymentId ?? null };
      const reply = await post<ChatResponse>("/assistant/chat", { message: clean, context });
      setMode(reply);
      if (reply.task?.kind === "payment_plan" && reply.task.status === "ready") setPlanQuote(reply.task.quote.quote_id);
      setTurns((t) => [...t, { id: ++counter.current, role: "bot", text: reply.reply, reply }]);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(text);
  }

  return (
    <>
      <button type="button" className="btn primary chat-toggle" aria-expanded={open} aria-controls="chat-panel" onClick={() => setOpen(!open)}>
        {open ? "Close assistant" : "Ask the assistant"}
      </button>
      {open ? (
        <section id="chat-panel" className="chat-panel" aria-label="Assistant chat">
          <div className="chat-head">
            <strong>StudyRoute assistant</strong>
            <Badge tone={mode?.mode === "llm" ? "info" : "warn"} title="Template mode answers from fixed templates and engine numbers. No model is called.">
              {mode?.mode === "llm" ? `Model: ${mode.model_version}` : "Template mode"}
            </Badge>
          </div>
          <div className="chat-log" aria-live="polite">
            <p className="small muted">
              I explain the engine's numbers. I cannot approve, submit, cancel or change anything.
              {scope.quoteId || scope.paymentId ? " I can see the quote or payment you have open." : " Tell me what you need to pay and I will plan it, or ask about a quote."}
            </p>
            {turns.map((turn, index) => (
              <div
                key={turn.id}
                className={`bubble ${turn.role}`}
                ref={index === turns.length - 1 && turn.role === "bot" ? newest : undefined}
              >
                {turn.reply ? <TaskView task={turn.reply.task} /> : null}
                {turn.text}
                {turn.reply ? <Details reply={turn.reply} paymentId={scope.paymentId} /> : null}
              </div>
            ))}
            {turns.length === 0 ? (
              <div className="chips">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="btn small" onClick={() => void ask(s)}>{s}</button>
                ))}
              </div>
            ) : null}
            <ErrorNotice error={error} />
          </div>
          <form className="chat-form" onSubmit={submit}>
            <label htmlFor="chat-input" className="sr-only">Your question</label>
            <input id="chat-input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about costs, deadlines, documents" maxLength={1000} />
            <button type="submit" className="btn primary" disabled={busy || !text.trim()}>Send</button>
          </form>
        </section>
      ) : null}
    </>
  );
}
