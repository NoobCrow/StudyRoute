# ml/: training the StudyRoute reader

The assistant's small language model is trained here. **You do not need any of this to run
StudyRoute**: the trained model is already committed in `backend/app/ai/nlu/model/`.

Everything is explained in [docs/AI_AGENT.md](../docs/AI_AGENT.md) (design, dataset card, limits) and the
measured results are in [docs/AI_EVALUATION.md](../docs/AI_EVALUATION.md).

| Path | What |
|------|------|
| `data/templates.py`, `templates_more.py`, `templates_more2.py` | the sentence templates for 14 intents |
| `data/render.py`, `generate.py`, `markup.py` | slot renderers (amounts, dates, ...), noise, inline annotation |
| `data/build_dataset.py` | builds `data/generated/*.jsonl.gz` and `manifest.json` (downloads Banking77, CC BY 4.0) |
| `data/hard_set.txt`, `data/blind_set.txt` | hand-written test messages, never used for training |
| `train.py` | fine-tunes a backbone on the GPU (intent head plus word-tagging head) |
| `export.py` | exports to int8 ONNX, calibrates, picks thresholds on the dev split, writes the manifest |
| `evaluate.py` | measures the shipped model against the rule-based reader, writes `docs/AI_EVALUATION.md` |
| `collect_ablation.py` | collects the backbone comparison into `submission/evidence/` |

```bash
python -m venv ml/.venv
ml/.venv/Scripts/python -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
ml/.venv/Scripts/python -m pip install -r ml/requirements.txt
backend/.venv/Scripts/python ml/data/build_dataset.py
ml/.venv/Scripts/python ml/train.py --backbone BAAI/bge-small-en-v1.5 --name bge --epochs 6 --lr 8e-5
ml/.venv/Scripts/python ml/export.py --name bge
backend/.venv/Scripts/python ml/evaluate.py
```

`ml/.venv/`, `ml/.cache/`, `ml/.tmp/` and `ml/runs/` (checkpoints) are git-ignored.
