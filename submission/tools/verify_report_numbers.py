"""Check the numbers in docs/TECHNICAL_DOCUMENTATION.md against the source evidence files.

    python submission/tools/verify_report_numbers.py        # from the repository root; standard library only

Each check has the value computed from the source and the text the report prints. It passes only if the
computed value equals the printed text AND the printed text appears in the report.
"""

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
report = (ROOT / "docs" / "TECHNICAL_DOCUMENTATION.md").read_text(encoding="utf-8")
ev = ROOT / "submission" / "evidence"
A = json.loads((ev / "ai_evaluation.json").read_text("utf-8"))
RL = json.loads((ev / "ai_rl_evaluation.json").read_text("utf-8"))
EX = json.loads((ev / "ai_explainer_evaluation.json").read_text("utf-8"))
RK = json.loads((ev / "ai_risk_operating_points.json").read_text("utf-8"))
RT = json.loads((ev / "ai_risk_training.json").read_text("utf-8"))
CM = json.loads((ev / "ai_risk_model_comparison.json").read_text("utf-8"))
TD = json.loads((ev / "tamper_demo.json").read_text("utf-8"))
rows: list[tuple[str, str, bool]] = []


def check(label: str, from_source: str, printed: str) -> None:
    ok = from_source == printed and printed in report
    rows.append((label, f"source -> {from_source!r}; report prints {printed!r}; in report: {printed in report}", ok))


def pct(v: float, digits: int = 1) -> str:
    return f"{100 * v:.{digits}f}%"


r, a = A["results"]["rules"], A["results"]["agent"]
check("blind intent, rules", pct(r["blind"]["routing_accuracy"]), "61.1%")
check("blind intent, model", pct(a["blind"]["routing_accuracy"]), "88.5%")
check("natural intent, rules", pct(r["natural"]["routing_accuracy"]), "40.1%")
check("natural intent, model", pct(a["natural"]["routing_accuracy"]), "95.1%")
check("held-out intent, rules", pct(r["test_heldout"]["routing_accuracy"]), "62.0%")
check("held-out intent, model", pct(a["test_heldout"]["routing_accuracy"]), "90.2%")
check("blind attacks blocked, rules", pct(r["blind"]["attack_blocked"]), "28.6%")
check("blind attacks blocked, model", pct(a["blind"]["attack_blocked"]), "92.9%")
check("held-out attacks blocked, rules", pct(r["test_heldout"]["attack_blocked"]), "52.1%")
check("held-out attacks blocked, model", pct(a["test_heldout"]["attack_blocked"]), "85.1%")
check("blind plan read exactly, model", pct(a["blind"]["task_success"], 0), "100%")
check("blind plan read exactly, rules", pct(r["blind"]["task_success"]), "57.6%")
check("blind harmless blocked, both", f"{pct(a['blind']['benign_blocked'])} for both" if a["blind"]["benign_blocked"] == r["blind"]["benign_blocked"] else "differ", "2.0% for both")
check("blind n", str(A["data"]["blind"]), "113")
check("natural n", str(A["data"]["natural"]), "680")
check("held-out n", f"{A['data']['test_heldout']:,}", "11,004")
check("training messages", f"{A['data']['train']:,}", "35,588")
check("reader latency median", f"{A['latency_cpu']['median_ms']:.0f} ms", "18 ms")
check("reader latency p95", f"{A['latency_cpu']['p95_ms']:.0f} ms", "57 ms")
check("reader size", f"{A['model_bytes'] / 1e6:.1f} MB", "33.8 MB")
check("reader training time", f"{A['model']['training']['train_seconds']:.0f} seconds", "238 seconds")

res = RL["results"]
learned, before = res["RL model (raw, before runtime review)"], res["before: plan as soon as the amount is known"]
rule, rnd = res["ask for everything, confirm every time"], res["random legal action"]
check("RL return, before", f"{before['return']:.3f}", "1.164")
check("RL return, random legal", f"{rnd['return']:.3f}", "1.236")
check("RL return, learned", f"{learned['return']:.3f}", "1.358")
check("RL return, hand rule", f"{rule['return']:.3f}", "1.343")
check("RL questions, before", f"{before['turns']:.2f}", "0.44")
check("RL questions, learned", f"{learned['turns']:.2f}", "1.17")
check("RL questions, hand rule", f"{rule['turns']:.2f}", "1.97")
check("RL wrong plans, before", pct(before["wrong_plan"]), "2.8%")
check("RL wrong plans, learned", pct(learned["wrong_plan"]), "0.8%")
check("RL wrong plans, random legal", pct(rnd["wrong_plan"]), "2.2%")
check("RL: fewer questions than the hand rule", f"{100 * (1 - learned['turns'] / rule['turns']):.0f}%", "40%")
check("RL episodes per policy", f"{RL['episodes_per_policy']:,}", "6,000")

sm = EX["shipped_model"]
check("explainer shown", pct(sm["shown_share"]), "80.9%")
check("explainer invented a figure", pct(sm["invented_a_figure_share"]), "0.4%")
check("explainer identical to draft", pct(sm["same_as_draft_share"]), "48.6%")
check("explainer raw figure precision", pct(sm["raw_output"]["figure_precision"]), "99.8%")
check("explainer raw figure recall", pct(sm["raw_output"]["figure_recall"]), "97.5%")
check("explainer test pairs", str(EX["test_pairs"]), "700")

routing = RK["routing used by the review desk"]
mh, ho = routing["medium or high (a person looks)"], routing["high only"]
check("router sent, medium+high", f"{mh['sent_to_a_person']:,}", "3,474")
check("router precision, medium+high", pct(mh["precision"]), "29.2%")
check("router recall, medium+high", pct(mh["recall"]), "56.5%")
check("router sent, high only", f"{ho['sent_to_a_person']:,}", "1,548")
check("router precision, high only (815 of 1,548)", f"{100 * ho['true_positives'] / ho['sent_to_a_person']:.1f}%", "52.6%")
check("router recall, high only", pct(ho["recall"]), "45.4%")
check("router accuracy, medium+high", pct(mh["accuracy"], 2), "99.68%")
check("router accuracy, high only", pct(ho["accuracy"], 2), "99.83%")
check("router accuracy, best F1", pct(RK["all payments"]["best_f1_point"]["accuracy"], 2), "99.86%")
check("accuracy of never flagging", pct(RK["all payments"]["never_flag_anything"]["accuracy"], 2), "99.82%")
check("router found in top 1%", pct(RT["results"]["mlp"]["test"]["found_in_top_1_percent"]), "63.2%")
check("random order found in top 1%", pct(RT["results"]["random_order"]["test"]["found_in_top_1_percent"]), "1.2%")
check("router average precision", f"{RT['results']['mlp']['test']['average_precision']:.3f}", "0.437")
check("router average precision against random", f"{round(RT['results']['mlp']['test']['average_precision'] / RT['results']['random_order']['test']['average_precision'], -1):.0f} times random", "240 times random")

models = {(m["model"], m["inputs"]): m for m in CM["models"]}


def ap(prefix: str, inputs: int, period: str) -> str:
    m = next(v for (n, i), v in models.items() if n.startswith(prefix) and int(i) == inputs)
    return f"{m[period]['average_precision']:.3f}"


check("XGBoost 13 tuning AP", ap("XGBoost", 13, "tuning"), "0.488")
check("XGBoost 13 test AP", ap("XGBoost", 13, "test"), "0.448")
check("RF 13 tuning AP", ap("random forest", 13, "tuning"), "0.475")
check("RF 13 test AP", ap("random forest", 13, "test"), "0.540")
check("NN 13 tuning AP", ap("neural network 128-64", 13, "tuning"), "0.438")
check("NN 13 test AP", ap("neural network 128-64", 13, "test"), "0.545")
check("NN 8 (shipped) tuning AP", ap("neural network 128-64", 8, "tuning"), "0.340")
check("NN 8 (shipped) test AP", ap("neural network 128-64", 8, "test"), "0.437")
check("logistic 8 tuning AP", ap("logistic regression", 8, "tuning"), "0.285")
check("logistic 8 test AP", ap("logistic regression", 8, "test"), "0.088")
check("comparison rows", str(len(CM["models"])), "24")
check("tamper-demo event", str(TD["edited_event"]["seq"]), "74")

failed = [row for row in rows if not row[2]]
print(f"{'PASS' if not failed else 'FAIL'}: {len(rows) - len(failed)} of {len(rows)} numeric checks agree with the source files")
for label, detail, _ in failed:
    print("  MISMATCH:", label, "|", detail)
