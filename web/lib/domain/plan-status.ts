import type { Tone } from "@/components/app/status";
import type { PlanView } from "@/lib/api/types";

/** How the engine's deadline status is worded and coloured. The status itself comes from the API. */
export const PLAN_STATUS: Record<PlanView["status"], { tone: Tone; text: string }> = {
  ON_TRACK: { tone: "ok", text: "On track" },
  TIGHT: { tone: "warn", text: "Tight" },
  AT_RISK: { tone: "warn", text: "At risk" },
  LATE: { tone: "danger", text: "Too late for normal settlement" },
};
