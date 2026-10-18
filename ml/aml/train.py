"""Train the review-priority model on the GPU and ship it with an honest report.

    ml/.venv/Scripts/python ml/aml/train.py            # GPU; after ml/aml/build.py
    ml/.venv/Scripts/python ml/aml/train.py --device cpu --rows 200000 --epochs 1   # smoke test

Two small networks learn from the same table: a plain logistic model (the simplest thing that
learns) and a two-layer network. Both are compared on the TEST period (the last fifth of the
timeline, never used for any choice) with two things that need no learning: random order, and
"the biggest amounts first". The one that does better on the TUNING period is written to
`backend/app/ai/risk/model/` as plain JSON with a SHA-256 manifest, so the app runs it in NumPy.

What the numbers mean: this model only ORDERS payments so that a bank reviewer looks at the odd ones
first. It was trained on public synthetic data whose laundering patterns were planted by a
generator, so it says nothing about real criminals and nothing about the families StudyRoute serves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai.risk.features import FEATURE_NAMES, FEATURES

DATA = ROOT / "ml" / "aml" / "data"
SHIP = ROOT / "backend" / "app" / "ai" / "risk" / "model"
AMOUNT = FEATURE_NAMES.index("amount_percentile")
PAIR_NEW = FEATURE_NAMES.index("pair_new")


def average_precision(y: np.ndarray, s: np.ndarray) -> float:
    order = np.argsort(-s, kind="stable")
    ys = y[order].astype(np.float64)
    hits = np.cumsum(ys)
    precision = hits / np.arange(1, len(ys) + 1)
    return float((precision * ys).sum() / max(ys.sum(), 1.0))


def roc_auc(y: np.ndarray, s: np.ndarray) -> float:
    ranks = np.empty(len(s))
    ranks[np.argsort(s, kind="stable")] = np.arange(1, len(s) + 1)
    positives = int(y.sum())
    negatives = len(y) - positives
    return float(
        (ranks[y == 1].sum() - positives * (positives + 1) / 2)
        / (positives * negatives)
    )


def recall_at(y: np.ndarray, s: np.ndarray, share: float) -> float:
    """Of all the laundering transactions, how many are in the top `share` of the ordering."""
    top = np.argsort(-s, kind="stable")[: max(1, int(len(s) * share))]
    return float(y[top].sum() / max(y.sum(), 1))


def report(y: np.ndarray, s: np.ndarray) -> dict[str, float]:
    return {
        "average_precision": round(average_precision(y, s), 4),
        "roc_auc": round(roc_auc(y, s), 4),
        "found_in_top_1_percent": round(recall_at(y, s, 0.01), 4),
        "found_in_top_5_percent": round(recall_at(y, s, 0.05), 4),
    }


def build(kind: str) -> nn.Module:
    if kind == "linear":
        return nn.Linear(FEATURES, 1)
    return nn.Sequential(
        nn.Linear(FEATURES, 128),
        nn.ReLU(),
        nn.Linear(128, 64),
        nn.ReLU(),
        nn.Linear(64, 1),
    )


def scores(model: nn.Module, x: torch.Tensor) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        out = [model(x[i : i + 262_144]).squeeze(1) for i in range(0, len(x), 262_144)]
    return torch.cat(out).float().cpu().numpy()


def fit(
    kind: str,
    xs: dict[str, torch.Tensor],
    ys: dict[str, np.ndarray],
    args: argparse.Namespace,
):
    torch.manual_seed(2026)
    model = build(kind).to(args.device)
    optimiser = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    loss_fn = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(args.pos_weight, device=args.device)
    )
    target = torch.as_tensor(ys["train"], dtype=torch.float32, device=args.device)
    best, best_state, history = -1.0, None, []
    for epoch in range(1, args.epochs + 1):
        model.train()
        order = torch.randperm(len(target), device=args.device)
        total = 0.0
        for start in range(0, len(order), args.batch):
            idx = order[start : start + args.batch]
            optimiser.zero_grad()
            loss = loss_fn(model(xs["train"][idx]).squeeze(1), target[idx])
            loss.backward()
            optimiser.step()
            total += loss.item() * len(idx)
        tuning = average_precision(ys["val"], scores(model, xs["val"]))
        history.append(
            {
                "epoch": epoch,
                "loss": round(total / len(order), 5),
                "val_ap": round(tuning, 4),
            }
        )
        print(
            f"  {kind} epoch {epoch}: loss {history[-1]['loss']}, tuning AP {tuning:.4f}",
            flush=True,
        )
        if tuning > best:
            best, best_state = (
                tuning,
                {k: v.detach().clone() for k, v in model.state_dict().items()},
            )
    model.load_state_dict(best_state)
    return model, best, history


def quantile_points(values: np.ndarray) -> list[float]:
    return [float(v) for v in np.quantile(values, np.linspace(0, 1, 101))]


def bands_of(
    tuning_scores: np.ndarray, flagged: np.ndarray
) -> dict[str, dict[str, float]]:
    high = float(np.quantile(tuning_scores, 0.999))
    medium = float(np.quantile(tuning_scores, 0.995))
    out: dict[str, dict[str, float]] = {}
    for name, low, up in (
        ("HIGH", high, np.inf),
        ("MEDIUM", medium, high),
        ("LOW", -np.inf, medium),
    ):
        inside = (tuning_scores >= low) & (tuning_scores < up)
        out[name] = {
            "from_logit": None if name == "LOW" else low,
            "payments": int(inside.sum()),
            "flagged_share": round(float(flagged[inside].mean()), 4)
            if inside.any()
            else 0.0,
        }
    return out


def layers_of(model: nn.Module) -> list[dict[str, list]]:
    linears = [m for m in model.modules() if isinstance(m, nn.Linear)]
    return [
        {
            "w": m.weight.detach().cpu().numpy().T.tolist(),
            "b": m.bias.detach().cpu().tolist(),
        }
        for m in linears
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch", type=int, default=16_384)
    parser.add_argument("--pos-weight", type=float, default=20.0)
    parser.add_argument(
        "--rows", type=int, default=0, help="only the first N training rows"
    )
    parser.add_argument("--name", default="studyroute-risk-v1")
    args = parser.parse_args()

    table = np.load(DATA / "table.npz")
    meta = json.loads((DATA / "table_meta.json").read_text(encoding="utf-8"))
    x_all = table["x"]
    y_all, split = table["y"], table["split"]
    raw_amount: dict[str, np.ndarray] = {}
    new_receiver: dict[str, np.ndarray] = {}
    xs, ys = {}, {}
    mean = np.asarray(meta["mean"], dtype=np.float32)
    std = np.asarray(meta["std"], dtype=np.float32)
    for name, code in (("train", 0), ("val", 1), ("test", 2)):
        mask = split == code
        part = (
            x_all[mask][: args.rows] if (args.rows and name == "train") else x_all[mask]
        )
        ys[name] = y_all[mask][: len(part)]
        raw_amount[name] = part[:, AMOUNT].copy()
        new_receiver[name] = part[:, PAIR_NEW] == 1
        xs[name] = torch.as_tensor((part - mean) / std, device=args.device)
    print(
        f"train {len(ys['train']):,} ({int(ys['train'].sum())} flagged), "
        f"tuning {len(ys['val']):,} ({int(ys['val'].sum())}), "
        f"test {len(ys['test']):,} ({int(ys['test'].sum())}) on {args.device}"
    )

    started = time.time()
    results: dict[str, dict] = {}
    trained: dict[str, nn.Module] = {}
    for kind in ("linear", "mlp"):
        model, tuning, history = fit(kind, xs, ys, args)
        trained[kind] = model
        test_scores = scores(model, xs["test"])
        only_new = new_receiver["test"]
        results[kind] = {
            "tuning_average_precision": round(tuning, 4),
            "test": report(ys["test"], test_scores),
            "test_first_payments_to_a_receiver_only": report(
                ys["test"][only_new], test_scores[only_new]
            ),
            "history": history,
        }
    rng = np.random.default_rng(2026)
    only_new = new_receiver["test"]
    for label, score in (
        ("biggest_amounts_first", raw_amount["test"]),
        ("random_order", rng.random(len(ys["test"]))),
    ):
        results[label] = {
            "test": report(ys["test"], score),
            "test_first_payments_to_a_receiver_only": report(
                ys["test"][only_new], score[only_new]
            ),
        }
    results["population"] = {
        "test_rows": len(ys["test"]),
        "test_flagged": int(ys["test"].sum()),
        "first_payments_rows": int(only_new.sum()),
        "first_payments_flagged": int(ys["test"][only_new].sum()),
        "first_payments_share_flagged": round(float(ys["test"][only_new].mean()), 5),
    }
    chosen = max(
        ("linear", "mlp"), key=lambda k: results[k]["tuning_average_precision"]
    )
    model = trained[chosen]
    tuning_scores = scores(model, xs["val"])
    shown = {
        k: {x: y for x, y in v.items() if x != "history"} for k, v in results.items()
    }
    print(json.dumps(shown, indent=1))
    print(f"shipping the {chosen} model; {time.time() - started:.0f} s")

    SHIP.mkdir(parents=True, exist_ok=True)
    body = {
        "model_id": args.name,
        "kind": chosen,
        "features": list(FEATURE_NAMES),
        "layers": layers_of(model),
        "mean": meta["mean"],
        "std": meta["std"],
        "quantiles": meta["quantiles"],
        "score_quantiles": quantile_points(tuning_scores),
        # The bands a person sees. Cut-offs and hit rates come from the TUNING period only: HIGH is
        # the top 0.1% of all payments and MEDIUM the next 0.4%. A hit rate is the share of payments
        # in that band that the data flags, which is what "high" means in practice.
        "bands": bands_of(tuning_scores, ys["val"]),
    }
    path = SHIP / "risk.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    source = json.loads((DATA / "external" / "SOURCE.json").read_text(encoding="utf-8"))
    manifest = {
        "model_id": args.name,
        "files": {"risk.json": hashlib.sha256(path.read_bytes()).hexdigest()},
        "kind": chosen,
        "trained_on": torch.cuda.get_device_name(0) if args.device == "cuda" else "cpu",
        "torch": torch.__version__,
        "data": {
            k: source[k]
            for k in ("dataset", "licence", "original", "sha256", "citation")
        },
        "rows": meta["rows"],
        "flagged": meta["positives"],
        "period_days": meta["period_days"],
        "split": "by time: first 60% train, next 20% tuning, last 20% test",
        "results": {
            k: {kk: vv for kk, vv in v.items() if kk != "history"}
            for k, v in results.items()
        },
        "note": "Orders payments for a human reviewer. Trained on public synthetic data; not a verdict.",
    }
    (SHIP / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    evidence = ROOT / "submission" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "ai_risk_training.json").write_text(
        json.dumps(
            {
                **manifest,
                "history": {k: results[k]["history"] for k in ("linear", "mlp")},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
