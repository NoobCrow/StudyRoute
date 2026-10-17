import { Notice } from "@/components/app/notice";
import { Chip, type Tone } from "@/components/app/status";
import type {
  AiFactor,
  AiReading,
  ReviewClock,
  ReviewPriority,
  ReviewStatusName,
} from "@/lib/api/types";

const STATUS_TONE: Record<ReviewStatusName, Tone> = {
  CLEARED_AUTO: "ok",
  OPEN: "warn",
  INFO_REQUESTED: "warn",
  CLEARED: "ok",
  DECLINED: "danger",
};

const STATUS_LABEL: Record<ReviewStatusName, string> = {
  CLEARED_AUTO: "No check needed",
  OPEN: "Waiting for the bank",
  INFO_REQUESTED: "Bank has a question",
  CLEARED: "Cleared",
  DECLINED: "Declined",
};

export function ReviewStatusChip({ status }: { status: ReviewStatusName }) {
  return <Chip tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Chip>;
}

/** "About 3 hours left" or "About 2 hours past the target", from the clock the API computed. */
export function clockText(clock: ReviewClock): string | null {
  if (!clock.running || clock.minutes_left === undefined) return null;
  const hours = Math.floor(Math.abs(clock.minutes_left) / 60);
  const minutes = Math.abs(clock.minutes_left) % 60;
  const span = hours > 0 ? `${hours} h ${minutes} min` : `${minutes} min`;
  return clock.minutes_left >= 0
    ? `About ${span} left of the bank's ${clock.target_hours}-hour target.`
    : `About ${span} past the bank's ${clock.target_hours}-hour target.`;
}

const CLOCK_TONE: Record<ReviewClock["state"], Tone> = {
  on_time: "ok",
  due_soon: "warn",
  overdue: "danger",
  not_running: "neutral",
};

const CLOCK_LABEL: Record<ReviewClock["state"], string> = {
  on_time: "On time",
  due_soon: "Due soon",
  overdue: "Overdue",
  not_running: "Not running",
};

export function ClockChip({ clock }: { clock: ReviewClock }) {
  return <Chip tone={CLOCK_TONE[clock.state]}>{CLOCK_LABEL[clock.state]}</Chip>;
}

const BAND_TONE: Record<ReviewPriority["band"], Tone> = {
  HIGH: "danger",
  MEDIUM: "warn",
  LOW: "neutral",
};

/** The small model's ordering hint. It never blocks or clears a payment, and the title says so. */
export function PriorityChip({ priority }: { priority: ReviewPriority | null }) {
  if (!priority) return <span className="text-muted-foreground text-xs">not scored</span>;
  return (
    <Chip
      tone={BAND_TONE[priority.band]}
      title={`AI risk reading: ${priority.band.toLowerCase()}, higher than ${priority.percentile}% of the practice data (model ${priority.model_id}). It decides who a person looks at. A person decides the answer.`}
    >
      Risk {priority.percentile} · {priority.band.toLowerCase()}
    </Chip>
  );
}

const BAND_WORDS: Record<AiReading["band"], string> = {
  HIGH: "high",
  MEDIUM: "medium",
  LOW: "low",
};

const LEVEL_WORDS: Record<AiFactor["level"], string> = {
  raises: "raises the score",
  neutral: "no effect",
  lowers: "lowers the score",
};

const LEVEL_TONE: Record<AiFactor["level"], Tone> = {
  raises: "warn",
  neutral: "neutral",
  lowers: "ok",
};

/** What a band meant in the practice data, in a sentence a parent can read. */
export function hitRateText(reading: AiReading): string {
  const rate = reading.hit_rate;
  if (rate === null || rate === undefined) return "";
  if (rate < 0.005) {
    return "In the practice data, payments rated like this were almost never flagged.";
  }
  const percent = rate >= 0.1 ? Math.round(rate * 100) : Math.round(rate * 1000) / 10;
  return `In the practice data, about ${percent}% of payments rated like this were flagged.`;
}

/**
 * Every payment's AI risk score, made of four factors (amount, frequency, timeline, person).
 * A low score shows no warning; a medium or high one shows a warning. Either way the payment needs
 * a person's authorization: the score never replaces it and never approves anything.
 */
export function AiReadingCard({
  reading,
  audience,
}: {
  reading: AiReading;
  audience: "parent" | "reviewer";
}) {
  const tone: Tone = reading.band === "HIGH" ? "danger" : reading.band === "MEDIUM" ? "warn" : "ok";
  return (
    <section aria-label="AI risk score" className="space-y-3 rounded-md border p-3 text-sm">
      <p className="flex flex-wrap items-center gap-2 font-medium">
        AI risk score {reading.score} out of 100{" "}
        <Chip tone={tone}>{BAND_WORDS[reading.band]} risk</Chip>
      </p>
      {reading.warning ? (
        <Notice tone={reading.band === "HIGH" ? "danger" : "warn"} title="Warning">
          The AI rates this payment as {BAND_WORDS[reading.band]} risk: it looks more unusual than{" "}
          {reading.score}% of the practice payments.{" "}
          {audience === "parent"
            ? "Read the reasons below before you authorize it."
            : "Check the reasons below before you answer."}
        </Notice>
      ) : (
        <p className="text-muted-foreground">
          No warning: nothing about this payment looks unusual.
        </p>
      )}
      <ul className="space-y-1" aria-label="What the score is made of">
        {reading.factors.map((factor) => (
          <li key={factor.code} className="flex flex-wrap items-center gap-2">
            <span className="w-24 font-medium">{factor.title}</span>
            <Chip tone={LEVEL_TONE[factor.level]}>{LEVEL_WORDS[factor.level]}</Chip>
            <span className="text-muted-foreground">{factor.plain}</span>
          </li>
        ))}
      </ul>
      <p className="text-muted-foreground text-xs">
        {hitRateText(reading)} Every payment needs a person&apos;s authorization, whatever its
        score. The AI only scores; it cannot clear, decline or approve anything, and it can be
        wrong.
      </p>
    </section>
  );
}
