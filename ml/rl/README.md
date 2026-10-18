# ml/rl/: reinforcement learning for the assistant's dialogue

A small policy decides how the assistant proceeds with a payment request: ask for the amount, the
date or the period, read the values back, or plan. Everything is explained in
[docs/AI_RL.md](../../docs/AI_RL.md) and measured in [docs/AI_RL_EVALUATION.md](../../docs/AI_RL_EVALUATION.md).
You do not need any of this to run StudyRoute: the trained policy is committed in
`backend/app/ai/dialogue/model/`.

| File | What |
|------|------|
| `build_bank.py` (run it through `run_build_bank.py`) | builds the simulator's observation bank: 6,000 simulated parents, every sentence they could say run through the REAL reader and checks (needs `onnxruntime`) |
| `bank/bank.jsonl.gz` | the bank |
| `env.py` | the simulator: a parent with a goal, five actions, a reward |
| `policies.py` | the hand-written policies to compare against, and the evaluation loop |
| `train_dqn.py` | trains with Double DQN and action masking; keeps the best checkpoint on validation goals |
| `export_policy.py` | writes the best run as `policy.json` plus a manifest with its SHA-256 |
| `evaluate_rl.py` | measures the shipped policy against the baselines and writes `docs/AI_RL_EVALUATION.md` |
| `run_all.sh` | trains every run used in the report |

```bash
backend/.venv/Scripts/python ml/rl/run_build_bank.py          # needs the backend environment
sh ml/rl/run_all.sh                                           # three seeds and three reward variants
ml/.venv/Scripts/python ml/rl/export_policy.py --names dm1 dm2 dm3
ml/.venv/Scripts/python ml/rl/evaluate_rl.py
```

The policy is tiny (30 inputs, two layers of 64, 5 outputs) and the simulator, not the network, is
the bottleneck, so a GPU does not make this faster; the script uses CUDA if it is there.
