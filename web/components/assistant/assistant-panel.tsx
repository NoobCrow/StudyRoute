"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronRight, Send } from "lucide-react";
import Link from "next/link";
import { useCallback } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useAssistant } from "@/components/assistant/assistant-context";
import { CloudSettings } from "@/components/assistant/cloud-settings";
import { TaskView } from "@/components/assistant/plan-card";
import { ErrorNotice } from "@/components/app/notice";
import { Chip } from "@/components/app/status";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { useCurrentChatScope } from "@/hooks/use-chat-scope";
import type { ChatAction, ChatResponse, DialogueChoice, Understanding } from "@/lib/api/types";
import { appHref } from "@/lib/links";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "I need to pay GBP 10,000 tuition by 28 October",
  "How often should I send GBP 800 a month for 9 months?",
  "Why is Provider B cheaper than A?",
  "What if the taka drops 10%?",
  "What do OUR, SHA and BEN mean?",
  "What documents do I need?",
  "What is the rent in Manchester?",
  "Which city fits BDT 200,000 a month?",
  "What should I do when I arrive?",
];

const SLOT_NAMES: Record<string, string> = {
  AMOUNT: "amount",
  CURRENCY: "currency",
  DATE: "date",
  DURATION: "period",
  CHARGE: "charge code",
  PURPOSE: "purpose",
  PROVIDER: "provider",
};

const NEXT_STEP: Record<string, string> = {
  RUN: "plan it",
  CONFIRM: "read the values back and ask you to confirm",
  ASK_AMOUNT: "ask for the amount",
  ASK_DATE: "ask for the date",
  ASK_MONTHS: "ask for the period",
};

const messageSchema = z.object({ message: z.string().trim().min(1).max(1000) });

function actionLink(action: ChatAction, paymentId?: string): { to: string; label: string } {
  if (action.tool === "create_draft") {
    const { quote_id: quote, provider_id: provider } = action.args;
    return {
      to: `/compare/?quote=${quote ?? ""}&provider=${provider ?? ""}`,
      label: "Review and confirm the draft",
    };
  }
  return {
    to: appHref(`/payments/${action.args.payment_id ?? paymentId ?? ""}`),
    label: "Open the payment to request approval",
  };
}

function Disclosure({ summary, children }: { summary: string; children: React.ReactNode }) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="group text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs">
        <ChevronRight
          className="size-3.5 transition-transform group-data-[state=open]:rotate-90"
          aria-hidden="true"
        />
        {summary}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1.5 space-y-1.5 pl-4 text-xs">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}

function GuardNote({ reply }: { reply: ChatResponse }) {
  const { status, failure, flags } = reply.guard;
  if (status === "cloud_unavailable" || (status === "passed" && flags.length === 0)) return null;
  const text: Record<string, string> = {
    policy_blocked: "Blocked by the safety check. Nothing was changed.",
    template_fallback: `A model reply was discarded (${failure ?? "guard"}). This is the engine's template answer.`,
    llm_unavailable: "The model was unavailable. This is the engine's template answer.",
  };
  return (
    <p className="text-xs">
      <Chip tone={status === "passed" ? "info" : "warn"}>Guard: {status.replace("_", " ")}</Chip>{" "}
      {text[status] ?? ""} {flags.length ? `Flags: ${flags.join(", ")}.` : ""}
    </p>
  );
}

function HowIRead({
  understanding,
  dialogue,
}: {
  understanding: Understanding;
  dialogue: DialogueChoice | null;
}) {
  const trained = understanding.source === "trained";
  const notes = [
    ...understanding.conflicts.map(
      (c) =>
        `the reader and the rules read the ${c.replace("_", " ")} differently, so I left it empty`,
    ),
    ...understanding.unreadable.map(
      (u) =>
        `I could not read "${u.split(":").slice(1).join(":")}" as a ${SLOT_NAMES[u.split(":")[0] ?? ""] ?? "value"}`,
    ),
  ];
  return (
    <Disclosure summary={`How I read this (${trained ? "trained reader" : "rules"})`}>
      <p>
        <Chip tone={trained ? "info" : "warn"}>
          {trained ? `Reader: ${understanding.model}` : "Rules only"}
        </Chip>{" "}
        Intent <strong>{understanding.intent}</strong>
        {understanding.model_intent && understanding.model_intent !== understanding.intent
          ? `; reader suggested ${understanding.model_intent}`
          : ""}
        {understanding.confidence !== null
          ? ` (${Math.round(understanding.confidence * 100)}% sure)`
          : ""}
        .
        {understanding.continued_earlier_task ? " I continued the task I asked about earlier." : ""}
      </p>
      {understanding.spans.length > 0 ? (
        <ul className="list-disc space-y-0.5 pl-4">
          {understanding.spans.map((s) => (
            <li key={`${s.start}-${s.label}`}>
              <code className="font-mono">{s.text}</code> is the {SLOT_NAMES[s.label] ?? s.label}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground">
          No amounts, dates or other values found in the words.
        </p>
      )}
      {notes.length > 0 ? <p>{notes.join(". ")}.</p> : null}
      {dialogue ? (
        <p>
          <Chip tone="info">Next step: {dialogue.action.replace("_", " ").toLowerCase()}</Chip> A
          small policy trained with reinforcement learning chose to{" "}
          {NEXT_STEP[dialogue.action] ?? dialogue.action}. It can only choose among steps that are
          safe for the values it holds, and none of them moves money.
        </p>
      ) : null}
      <p className="text-muted-foreground">
        The small reader marks payment details; it is not the cloud language model. The engine
        calculates amounts. A connected cloud model writes the reply.
      </p>
    </Disclosure>
  );
}

function Details({
  reply,
  paymentId,
  onAnswer,
}: {
  reply: ChatResponse;
  paymentId?: string;
  onAnswer?: (text: string) => void;
}) {
  const proposals =
    reply.task?.kind === "payment_plan" && reply.task.status === "ready"
      ? []
      : reply.proposed_actions;
  return (
    <div className="mt-2 space-y-1.5">
      <GuardNote reply={reply} />
      {reply.task?.status === "needs_confirmation" && onAnswer ? (
        <div
          className="flex flex-wrap gap-2 py-1"
          role="group"
          aria-label="Confirm what I understood"
        >
          <Button type="button" size="sm" onClick={() => onAnswer("yes")}>
            Yes, plan it
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="bg-card"
            onClick={() => onAnswer("no")}
          >
            No, change something
          </Button>
        </div>
      ) : null}
      {reply.mode !== "unavailable" ? (
        <HowIRead understanding={reply.understanding} dialogue={reply.dialogue} />
      ) : null}
      {reply.facts.length > 0 ? (
        <Disclosure summary={`Facts used (${reply.facts.length})`}>
          <ul className="space-y-0.5">
            {reply.facts.map((fact) => (
              <li key={fact.id}>
                <code className="font-mono">{fact.id}</code> {fact.label}:{" "}
                <strong>{fact.value}</strong>
              </li>
            ))}
          </ul>
        </Disclosure>
      ) : null}
      {proposals.map((action) => {
        const link = actionLink(action, paymentId);
        return (
          <p key={`${action.tool}-${link.to}`} className="text-xs">
            <Chip tone="info">Proposal only</Chip>{" "}
            {action.tool === "create_draft" ? "Create a draft" : "Request approval"}.{" "}
            <Link href={link.to} className="text-primary underline">
              {link.label}
            </Link>
            . A human must confirm; approval stays with you.
          </p>
        );
      })}
      <Disclosure summary="Debug: what the model sees (masked)">
        <pre className="bg-muted max-h-48 overflow-auto rounded p-2 font-mono text-[11px] whitespace-pre-wrap">
          {reply.debug.masked_prompt}
        </pre>
      </Disclosure>
    </div>
  );
}

/** The conversation, the suggestions and the message box. It sits in a side sheet. */
export function AssistantPanel() {
  const scope = useCurrentChatScope();
  const { turns, busy, connecting, error, ask } = useAssistant();
  const form = useForm<z.infer<typeof messageSchema>>({
    resolver: zodResolver(messageSchema),
    defaultValues: { message: "" },
  });
  const newest = useCallback((node: HTMLDivElement | null) => {
    node?.scrollIntoView?.({ block: "start" });
  }, []);

  async function onSubmit(values: z.infer<typeof messageSchema>) {
    form.reset({ message: "" });
    await ask(values.message);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 border-b px-4 py-2">
        <CloudSettings />
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3" aria-live="polite">
        <p className="text-muted-foreground text-xs">
          I explain the engine&apos;s numbers. I cannot approve, submit, cancel or change anything.
          {scope.quoteId || scope.paymentId
            ? " I can see the quote or payment you have open."
            : " Tell me what you need to pay and I will plan it, or ask about a quote."}
        </p>
        {turns.map((turn, index) => (
          <div
            key={turn.id}
            ref={index === turns.length - 1 && turn.role === "bot" ? newest : undefined}
            className={cn(
              "animate-rise max-w-[92%] rounded-xl px-3 py-2 text-sm",
              turn.role === "me"
                ? "bg-success-soft text-success-soft-foreground ml-auto"
                : "bg-muted",
            )}
          >
            {turn.reply ? <TaskView task={turn.reply.task} /> : null}
            <p className="whitespace-pre-wrap">{turn.text}</p>
            {turn.reply ? (
              <Details
                reply={turn.reply}
                paymentId={scope.paymentId}
                onAnswer={index === turns.length - 1 ? (text) => void ask(text) : undefined}
              />
            ) : null}
          </div>
        ))}
        {turns.length === 0 ? (
          <div className="stagger flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <Button
                key={s}
                type="button"
                variant="outline"
                size="sm"
                className="bg-card animate-rise h-auto py-1.5 text-left whitespace-normal"
                onClick={() => void ask(s)}
              >
                {s}
              </Button>
            ))}
          </div>
        ) : null}
        {busy ? (
          <p className="text-muted-foreground flex items-center gap-2 text-xs" role="status">
            <span aria-hidden="true" className="flex gap-1">
              <span className="bg-primary animate-typing-dot size-1.5 rounded-full" />
              <span className="bg-primary animate-typing-dot size-1.5 rounded-full [animation-delay:0.15s]" />
              <span className="bg-primary animate-typing-dot size-1.5 rounded-full [animation-delay:0.3s]" />
            </span>
            Thinking with the engine&apos;s numbers...
          </p>
        ) : null}
        <ErrorNotice error={error} />
      </div>
      <form onSubmit={form.handleSubmit(onSubmit)} className="flex items-center gap-2 border-t p-3">
        <label htmlFor="chat-input" className="sr-only">
          Your question
        </label>
        <Input
          id="chat-input"
          placeholder="Ask about costs, deadlines, documents"
          maxLength={1000}
          autoComplete="off"
          {...form.register("message")}
        />
        <Button
          type="submit"
          size="icon"
          className="group"
          disabled={busy || connecting}
          aria-label="Send"
        >
          <Send
            aria-hidden="true"
            className="transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
          />
        </Button>
      </form>
    </div>
  );
}
