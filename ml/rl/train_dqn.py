"""Train the dialogue policy with Double DQN against the simulator.

    ml/.venv/Scripts/python ml/rl/train_dqn.py --name dm1 --seed 1

A small multilayer network scores the five actions from the state's 29 numbers. Only legal
actions are ever tried or used (the safety rules are plain code in state.py, and the Bellman
target maximises over the legal actions of the next state only). The best checkpoint on the
VALIDATION goals is kept; the test goals are never looked at here.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ml" / "rl"), str(ROOT / "backend")]

import torch  # noqa: E402
from app.ai.dialogue.state import (  # noqa: E402
    ACTIONS,
    FEATURES,
    Action,
    DialogueState,
    features,
    legal_actions,
)
from env import DialogueEnv, Rewards, load_bank, split_bank  # noqa: E402
from policies import evaluate  # noqa: E402
from torch import nn  # noqa: E402


def build_net() -> nn.Module:
    return nn.Sequential(
        nn.Linear(FEATURES, 64),
        nn.ReLU(),
        nn.Linear(64, 64),
        nn.ReLU(),
        nn.Linear(64, len(ACTIONS)),
    )


def greedy(net: nn.Module, device: torch.device):
    def policy(state: DialogueState, legal: list[bool], rng: random.Random) -> Action:
        with torch.no_grad():
            q = net(torch.tensor([features(state)], dtype=torch.float32, device=device))[0]
        scores = [float(q[a]) if legal[a] else float("-inf") for a in ACTIONS]
        return Action(max(range(len(scores)), key=scores.__getitem__))

    return policy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="dm1")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--episodes", type=int, default=100_000)
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--wrong-amount", type=float, default=-2.0)
    parser.add_argument("--turn-cost", type=float, default=-0.05)
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    rewards = Rewards(wrong_amount=args.wrong_amount, turn_cost=args.turn_cost)
    bank = split_bank(load_bank())
    env = DialogueEnv(bank["train"], rewards, seed=args.seed)
    net, target = build_net().to(device), build_net().to(device)
    target.load_state_dict(net.state_dict())
    optimiser = torch.optim.Adam(net.parameters(), lr=args.lr)
    replay: deque = deque(maxlen=100_000)
    rng = random.Random(args.seed)
    out = ROOT / "ml" / "runs" / "rl" / args.name
    out.mkdir(parents=True, exist_ok=True)
    curve, best, steps, started = [], float("-inf"), 0, time.time()

    for episode in range(1, args.episodes + 1):
        epsilon = max(0.03, 1.0 - episode / (0.4 * args.episodes))
        state, done = env.reset(), False
        while not done:
            legal = legal_actions(state)
            if rng.random() < epsilon:
                action = rng.choice([a for a in ACTIONS if legal[a]])
            else:
                action = greedy(net, device)(state, legal, rng)
            nxt, reward, done, _ = env.step(action)
            replay.append(
                (features(state), int(action), reward, features(nxt), done, legal_actions(nxt))
            )
            state, steps = nxt, steps + 1
            if len(replay) >= 2_000 and steps % 2 == 0:
                batch = rng.sample(replay, args.batch)
                s, a, r, s2, d, m2 = zip(*batch, strict=True)
                s_t = torch.tensor(s, dtype=torch.float32, device=device)
                s2_t = torch.tensor(s2, dtype=torch.float32, device=device)
                a_t = torch.tensor(a, dtype=torch.long, device=device)
                r_t = torch.tensor(r, dtype=torch.float32, device=device)
                d_t = torch.tensor(d, dtype=torch.float32, device=device)
                m_t = torch.tensor(m2, dtype=torch.bool, device=device)
                with torch.no_grad():
                    online = net(s2_t).masked_fill(~m_t, float("-inf"))
                    best_next = online.argmax(dim=1, keepdim=True)  # Double DQN
                    q_next = target(s2_t).gather(1, best_next).squeeze(1)
                    y = r_t + args.gamma * q_next * (1.0 - d_t)
                q = net(s_t).gather(1, a_t.unsqueeze(1)).squeeze(1)
                loss = nn.functional.smooth_l1_loss(q, y)
                optimiser.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
                optimiser.step()
            if steps % 500 == 0:
                target.load_state_dict(net.state_dict())
        if episode % 5_000 == 0:
            result = evaluate(
                greedy(net, device), bank["val"], rewards, 4 * len(bank["val"]), seed=99
            )
            curve.append(
                {
                    "episode": episode,
                    "epsilon": round(epsilon, 3),
                    "val_return": result.mean,
                    "val_wrong_plan": result.wrong_plan,
                    "val_turns": result.turns,
                    "seconds": round(time.time() - started, 1),
                }
            )
            print(json.dumps(curve[-1]))
            if result.mean > best:
                best = result.mean
                torch.save(net.state_dict(), out / "best.pt")
    (out / "curve.json").write_text(json.dumps(curve, indent=1), encoding="utf-8")
    config = {
        "args": vars(args),
        "rewards": rewards.__dict__,
        "best_val_return": best,
        "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
        "torch": torch.__version__,
        "train_seconds": round(time.time() - started, 1),
        "transitions": steps,
        "features": FEATURES,
    }
    (out / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("best validation return", round(best, 4), "saved", out / "best.pt")


if __name__ == "__main__":
    main()
