import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import type { Health } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { BrandMark } from "../components/BrandMark";
import { ThemeToggle } from "../components/ThemeToggle";
import { ErrorNotice, Field, Notice } from "../components/Ui";
import { loadHealth } from "../health";

export function LoginScreen() {
  const { user, ready, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    loadHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  if (ready && user) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate("/");
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  const demo = health?.demo;
  return (
    <main className="page">
      <div className="row between login-top">
        <span className="brand"><BrandMark />StudyRoute</span>
        <ThemeToggle />
      </div>
      <div className="grid two">
        <form className="card" onSubmit={submit} aria-labelledby="signin-title">
          <p className="eyebrow">Made for families in Bangladesh</p>
          <h1 id="signin-title">Sign in to StudyRoute</h1>
          <p className="muted">
            An assistant for paying tuition and living costs abroad from Bangladesh. The engine
            calculates, the AI explains, a human approves, and every step is logged.
          </p>
          <ErrorNotice error={error} />
          <Field label="Email" htmlFor="email">
            <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </Field>
          <Field label="Password" htmlFor="password">
            <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          <button type="submit" className="btn primary" disabled={busy}>Sign in</button>
        </form>
        <aside className="card" aria-label="Sandbox demo accounts">
          <h2>Try the sandbox</h2>
          <Notice tone="info">
            Every account, rate, fee and provider here is synthetic. No real money moves and no
            real bank is contacted.
          </Notice>
          {demo ? (
            <>
              <p className="small">
                Demo accounts. Password <code>{demo.password}</code>, MFA code <code>{demo.mfa_code}</code>.
              </p>
              <ul className="chip-list">
                {demo.accounts.map((account) => (
                  <li key={account}>
                    <button type="button" className="btn small ghost" onClick={() => { setEmail(account); setPassword(demo.password); }}>
                      {account}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted small">Ask the team for a demo account.</p>
          )}
          <p className="small muted">
            AI mode: {health ? (health.ai_mode === "template" ? "template mode (no model key set)" : health.ai_mode) : "checking"}.
          </p>
        </aside>
      </div>
    </main>
  );
}
