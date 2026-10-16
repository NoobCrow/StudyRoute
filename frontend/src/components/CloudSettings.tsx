import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { CloudAvailability, CloudConnection } from "../api/types";
import { useAssistant } from "./AssistantContext";

function WaitNotice({ availability }: { availability: CloudAvailability }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!availability.retry_at) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [availability.retry_at]);
  const deadline = availability.retry_at ? Date.parse(availability.retry_at) : NaN;
  const remaining = Math.max(0, Math.ceil((deadline - now) / 1000));
  return <div className="notice" role="status">
    <p>{availability.message}</p>
    <p aria-live="off">{Number.isFinite(deadline)
      ? remaining > 0 ? `Provider-reported retry: ${Math.floor(remaining / 60)}m ${remaining % 60}s remaining.`
        : "The reported wait has ended. You may retry; availability is not guaranteed."
      : "The provider did not supply an exact retry time. No countdown is available."}</p>
    <p>Continue now by connecting Gemini or Groq below. Their own limits still apply.</p>
  </div>;
}

export function CloudSettings() {
  const { mode, connected, busy, connecting, connectionResult, connect, disconnect } = useAssistant();
  const [provider, setProvider] = useState<CloudConnection["provider"]>("gemini");
  const [key, setKey] = useState("");
  const [consent, setConsent] = useState(false);
  async function onConnect(event: FormEvent) {
    event.preventDefault();
    if (!consent || key.trim().length < 10) return;
    const secret = key.trim(); setKey("");
    await connect({ provider, api_key: secret, consent: true });
  }
  return <section className="small" aria-label="Cloud connection">
    {mode?.availability ? <WaitNotice availability={mode.availability} /> : null}
    <details open={Boolean(mode?.availability || connected || connecting || connectionResult)}>
      <summary>AI connection settings</summary>
      <p>Without your key, chat uses the operator&apos;s Hugging Face Space if configured. No model downloads to your PC. Free quotas and queues apply.</p>
      <p>Questions, recent conversation and masked app facts go to the selected service. Masking cannot remove every detail. Use synthetic data only.</p>
      {connected ? <div role="status"><p>Connected to {connected.provider} / {connected.model}.</p>
        <button className="btn small" type="button" disabled={busy || connecting} onClick={disconnect}>Remove key and use default provider</button></div> : null}
      <form onSubmit={onConnect}>
        <label htmlFor="ai-provider">Provider</label>
        <select id="ai-provider" value={provider} disabled={busy || connecting}
          onChange={(e) => { setProvider(e.target.value as CloudConnection["provider"]); setKey(""); }}>
          <option value="gemini">Gemini</option><option value="groq">Groq</option>
        </select>
        <label htmlFor="ai-api-key">API key</label>
        <input id="ai-api-key" type="password" autoComplete="off" spellCheck={false} value={key}
          maxLength={512} minLength={10} required disabled={busy || connecting} onChange={(e) => setKey(e.target.value)} />
        <label><input type="checkbox" checked={consent} disabled={busy || connecting} onChange={(e) => setConsent(e.target.checked)} />
          I agree to send chat context to this provider. The synthetic connection test may consume quota.</label>
        <button className="btn small" type="submit" disabled={busy || connecting || !consent || key.trim().length < 10}>
          {connecting ? "Testing connection…" : "Test and connect"}</button>
      </form>
      {connectionResult?.ok ? <p role="status">Connection verified. Your conversation is kept; send your next question.</p> : null}
      {connectionResult?.availability ? <WaitNotice availability={connectionResult.availability} /> : null}
      <p>Keys stay in memory, not chat history or browser storage. Reload, sign out or remove the key to clear it. Use HTTPS except on localhost. Never paste keys into chat.</p>
    </details>
  </section>;
}
