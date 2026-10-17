"use client";

import { useAssistant } from "@/components/assistant/assistant-context";
import { AssistantPanel } from "@/components/assistant/assistant-panel";
import { Chip } from "@/components/app/status";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

/** The assistant opens in a side sheet; the conversation survives closing it. */
export function AssistantSheet({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { mode, connected } = useAssistant();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <SheetTitle>StudyRoute assistant</SheetTitle>
          <div className="flex flex-wrap gap-1.5">
            <Chip
              tone={mode?.mode === "llm" ? "info" : "warn"}
              title={
                mode?.mode === "llm"
                  ? "A configured external language model explains checked engine facts."
                  : mode?.mode === "unavailable"
                    ? "No model answer was returned. Check cloud connection settings."
                    : "Configure Hugging Face or connect a provider to use cloud chat."
              }
            >
              {connected
                ? `${connected.provider}: ${connected.model}`
                : mode?.mode === "llm"
                  ? `Model: ${mode.model_version}`
                  : mode?.mode === "unavailable"
                    ? "Cloud unavailable"
                    : mode?.mode === "template"
                      ? "Offline assistant"
                      : "Cloud assistant"}
            </Chip>
            {mode?.understanding.source === "trained" ? (
              <Chip
                tone="info"
                title="A small trained model marks the words that carry a value. Plain code checks them and the engine calculates."
              >
                Trained reader
              </Chip>
            ) : null}
          </div>
          <SheetDescription className="sr-only">
            I explain the engine&apos;s numbers. I cannot approve, submit, cancel or change
            anything.
          </SheetDescription>
        </SheetHeader>
        <AssistantPanel />
      </SheetContent>
    </Sheet>
  );
}
