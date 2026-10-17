# Questions to prepare for (online review and the final's Q&A)

Ten questions a hard judge is likely to ask, with what the repository can honestly say. Every
claim points to a file. Where something was **not done**, the answer says so: say the same on the
day, and do not improvise a number. Questions 1 and 5 touch the assistant: re-read them after the
assistant work is final and update them to match.

## 1. Why does this need AI?

- **Honest answer:** the money maths does not, and we kept it out of the model on purpose: a
  deterministic engine computes every number. The AI reads untidy wording ("ten thousand pounds,
  last date end of November") into an amount, a currency and a date, decides when to ask a
  question, and explains the result. Plain code checks every value it proposes.
- **Evidence:** on 113 messages written by hand after the model was frozen, the right intent
  88.5% against 61.1% for the old rules, and a plan request read exactly 100% against 57.6%
  (`docs/AI_EVALUATION.md`).
- **Say plainly:** the data is mostly synthetic, the sample is small (about plus or minus 7
  points), and the only baseline beaten is our own rule-based reader.

## 2. What stops Flywire, Wise or a bank from copying this?

- **Honest answer:** nothing stops anyone copying a fee-ranking engine. What we offer is a
  payer-side tool that is independent of any provider: it compares, plans the deadline, and puts a
  human approval bound to the summary hash in front of the money, with a tamper-evident log. A
  provider has little reason to rank its competitors.
- **Say plainly:** they have real rails and university integrations; we have neither, and no
  partner yet.

## 3. What happens when the agent makes a financially harmful decision?

- **Answer:** it cannot approve, submit, cancel, allowlist, or change a limit or a rule. Only a
  human parent with a fresh MFA proof, bound to the payment and the hash of the summary they saw,
  can approve. The worst thing an AI error can produce is a wrong quote card, which expires in five
  minutes and says "Indicative. Confirm with your AD bank."
- **Evidence:** the permission matrix is generated from the code and checked by a test
  (`docs/SECURITY_SELF_ASSESSMENT.md` section 1, `test_api_ai_rbac.py`); risks R9, R18 and R32.

## 4. Where is your quantitative evidence?

- **Measured:** engine arithmetic (24 scenarios mapped to tests, `docs/TEST_CASES.md`); the
  trained reader against the rules with confidence intervals (`docs/AI_EVALUATION.md`); the policy
  against simulated parents (`docs/AI_RL_EVALUATION.md`); attack probes and a browser audit under
  the strict CSP (`docs/SECURITY_TESTING.md`); a real `docker compose` run from the archive
  (`submission/evidence/docker_run.txt`).
- **Not measured:** any real provider's quote, any real user. The fees, rates and city costs are
  invented (`docs/OPEN_QUESTIONS.md`, section C). Say that first; do not let a judge find it.
- **Not done, and how to do it:** take 3 dated public quotes for one corridor, enter the same
  inputs, publish the difference. Or time five outsiders on "pay GBP 10,000 by 28 October" against
  a spreadsheet.

## 5. What happens when your model or an API fails?

- **Answer:** with no key the assistant runs in labelled template mode, so the demo never depends
  on a network. A person can add their own Gemini or Groq key in the assistant settings (saved
  encrypted, with consent); an operator can instead point it at their own Hugging Face Space. If a
  model returns a figure the engine did not produce, the number guard rejects the answer; if a
  provider is unreachable, out of quota or rejects the key, the person sees a typed message (with
  the provider's own retry time when it gives one) and nothing is done. `NLU_MODE=off` and
  `DIALOGUE_MODE=off` switch the trained parts off, and a changed model file is refused at start-up.
- **Say plainly:** the Gemini, Groq and Hugging Face paths were tested with mocked HTTP only; none
  has run against a real provider (risks R15 and R48, `docs/ASSISTANT_CLOUD_VERIFICATION.json`).
  Update this line after a real run with `python -m app.scripts.check_ai`.

## 6. What is the strongest baseline you beat?

- **Honest answer:** our own regex reader plus its policy filter. Held-out wording: 62.0% against
  90.2% routing; blind set 61.1% against 88.5%.
- **Not run:** a classical baseline (TF-IDF with logistic regression) or a few-shot general model.
  Do not claim to beat them.

## 7. Which part actually works today?

- **Works, with evidence:** the full sandbox flow from one sentence to a settled simulated payment
  (the 14-step demo, `submission/evidence/sandbox_operation_log.txt`), approval and audit controls,
  Docker from the unzipped archive, 1,223 backend and 406 web tests.
- **Does not exist:** a live bank, a live FX feed, real KYC, real sanctions screening, verified
  Bangladesh Bank limits.

## 8. Why should a financial institution trust it?

- **Honest answer:** it should not yet, and the repository says what it would need first: an
  outside security review, a real KYC and sanctions provider, verified regulatory values, and
  real-quote calibration. What exists is a design that is easy to review: the permission matrix,
  44 listed risks with residuals, a hash-chained audit log with an external anchor.

## 9. What is your most serious unresolved weakness?

- **Honest answer:** every number is invented. The ranking shows how the engine works, not what a
  real provider charges, and a user could mistake it for real. Mitigation: a "Not verified" badge
  on every unverified value, "invented for the sandbox" on cost figures, no claim of a live bank or
  live rates. Fixing it needs a partner or published fee data.

## 10. How was this built, and can each of you explain every module?

- **Not for the assistant to answer.** The rules require work done independently and third-party
  parts licensed (`docs/THIRD_PARTY.md`). Write down, before the day:
  - who wrote which part, and which tools were used (including any AI coding assistant);
  - which member can explain, from the code, each of these flows end to end: the fee engine and
    ranking, the deadline planner, the approval with MFA and summary hash, the audit chain and its
    anchor, the trained reader's checks.
- Every member should be able to run `python -m app.scripts.demo_flow` and explain each line.

## Likely follow-ups (one line each)

- **Why only Bangladesh to abroad?** The corridor is where we could name the rules and the pain;
  other corridors are configuration, not code (`config/rules.yaml`).
- **Credit building?** Named in Topic C and not built. Multi-currency is shown with simulated
  accounts only.
- **Why smart escrow and a bank network?** Extras beyond Topic C. They run on a simulated chain
  and ledger, and the AI has no permission in either. They are not the core claim.
- **Is it legal?** We never say so. Every limit is a placeholder marked "Not verified".
