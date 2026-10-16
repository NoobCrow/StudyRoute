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
  const { mode } = useAssistant();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <SheetTitle>StudyRoute assistant</SheetTitle>
          <div className="flex flex-wrap gap-1.5">
            <Chip
              tone={mode?.mode === "llm" ? "info" : "warn"}
              title="Template mode answers from fixed templates and engine numbers. No model is called."
            >
              {mode?.mode === "llm" ? `Model: ${mode.model_version}` : "Template mode"}
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
