"""After bootstrap: verify the original reader, explainer and risk models load locally."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ai.explainer.runtime import load_explainer
from app.ai.nlu.runtime import load_reader
from app.ai.risk.scorer import load_scorer

for label, loader in [
    ("reader", load_reader),
    ("explainer", load_explainer),
    ("risk", load_scorer),
]:
    model = loader("auto")
    if model is None:
        raise SystemExit(f"Local {label} model did not load")
    print(f"PASS local {label}: {model.model_id}")
    del model
