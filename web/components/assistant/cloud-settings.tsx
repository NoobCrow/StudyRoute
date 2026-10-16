"use client";

import { useEffect, useState } from "react";

import { useAssistant } from "@/components/assistant/assistant-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { CloudAvailability, CloudConnection } from "@/lib/api/types";

/** Only provider-reported absolute times; no made-up daily reset or browser auto-retry. */
export function WaitNotice({ availability }: { availability: CloudAvailability }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!availability.retry_at) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [availability.retry_at]);
  const deadline = availability.retry_at ? Date.parse(availability.retry_at) : NaN;
  const remaining = Math.max(0, Math.ceil((deadline - now) / 1000));
  return (
    <div className="bg-muted rounded-md p-2 text-xs" role="status">
      <p>{availability.message}</p>
      <p className="mt-1 font-medium" aria-live="off">
        {Number.isFinite(deadline)
          ? remaining > 0
            ? `Provider-reported retry: ${Math.floor(remaining / 60)}m ${remaining % 60}s remaining.`
            : "The reported wait has ended. You may retry; availability is not guaranteed."
          : "The provider did not supply an exact retry time. No countdown is available."}
      </p>
      <p className="mt-1">
        Continue now by connecting Gemini or Groq below. Their own limits still apply.
      </p>
    </div>
  );
}

export function CloudSettings() {
  const { mode, connected, busy, connecting, connectionResult, connect, disconnect } =
    useAssistant();
  const [provider, setProvider] = useState<CloudConnection["provider"]>("gemini");
  const [key, setKey] = useState("");
  const [consent, setConsent] = useState(false);
  const unavailable = mode?.availability;
  const problem = connectionResult?.availability;

  async function onConnect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!consent || !key.trim()) return;
    const secret = key.trim();
    setKey("");
    await connect({ provider, api_key: secret, consent: true });
  }

  return (
    <section aria-label="Cloud connection" className="space-y-2 border-t pt-3">
      {unavailable ? <WaitNotice availability={unavailable} /> : null}
      <details open={Boolean(unavailable || connected || connecting || connectionResult)}>
        <summary className="cursor-pointer text-xs font-medium">AI connection settings</summary>
        <div className="mt-2 space-y-2 text-xs">
          <p>
            Without your key, chat uses the operator&apos;s Hugging Face Space if configured. It is
            cloud-hosted, not a model downloaded to your PC. Free quota and queues apply.
          </p>
          <p>
            Questions, bounded recent conversation and masked app facts are sent to the selected
            service. Masking reduces exposure but cannot remove every detail. Use synthetic data;
            never paste passports, account details or keys into chat.
          </p>
          {connected ? (
            <div role="status" className="space-y-2">
              <p>
                Connected to {connected.provider} / {connected.model} — saved for your account.
              </p>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy || connecting}
                onClick={disconnect}
              >
                Remove saved key and use default provider
              </Button>
            </div>
          ) : null}
          {connected?.verified === false ? (
            <p role="status">
              Saved key has not passed a provider test. Quota or validity may still need attention.
            </p>
          ) : null}
          <form onSubmit={onConnect} className="space-y-2">
            <label htmlFor="ai-provider" className="block">
              Provider
            </label>
            <select
              id="ai-provider"
              value={provider}
              disabled={busy || connecting}
              onChange={(e) => {
                setProvider(e.target.value as CloudConnection["provider"]);
                setKey("");
              }}
              className="bg-background w-full rounded-md border p-2 text-sm"
            >
              <option value="gemini">Gemini</option>
              <option value="groq">Groq</option>
            </select>
            <label htmlFor="ai-api-key" className="block">
              API key
            </label>
            <Input
              id="ai-api-key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={key}
              maxLength={512}
              minLength={10}
              required
              disabled={busy || connecting}
              onChange={(e) => setKey(e.target.value)}
              placeholder="Enter your provider API key"
            />
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={consent}
                disabled={busy || connecting}
                onChange={(e) => setConsent(e.target.checked)}
              />
              <span>
                I agree to store this key encrypted on the server for my account and send chat
                context to this provider. The connection test uses a small synthetic request and may
                consume quota.
              </span>
            </label>
            <Button
              type="submit"
              size="sm"
              disabled={busy || connecting || !consent || key.trim().length < 10}
            >
              {connecting ? "Saving connection…" : "Test and save connection"}
            </Button>
          </form>
          {connectionResult?.ok ? (
            <p role="status">
              {connectionResult.verified
                ? "Connection verified and saved. Your conversation is kept."
                : "Key saved, but the provider test was not verified. Provider limits still apply."}
            </p>
          ) : null}
          {problem ? <WaitNotice availability={problem} /> : null}
          <p className="text-muted-foreground">
            Your key is encrypted on the server, never returned in chat history or browser storage.
            It survives refresh, new tabs and sign-out. Use Remove saved key to delete it. Use HTTPS
            except on localhost. Anyone sharing this account can use its saved key and quota; do not
            save personal keys in shared demo accounts. Keep the server encryption secret backed up.
          </p>
        </div>
      </details>
    </section>
  );
}
