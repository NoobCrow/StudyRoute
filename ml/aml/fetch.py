"""Check the public data set that the review-priority model learns from, and record where it is from.

    ml/.venv/Scripts/python ml/aml/fetch.py

The data is "IBM Transactions for Anti Money Laundering (AML)", HI-Small: synthetic transactions
made by IBM Research's generator, published under the Community Data License Agreement, Sharing,
Version 1.0 (CDLA-Sharing-1.0). It was downloaded from the Hugging Face mirror
`OsamaMIT/IBM-AML-HI-Small` (the original is on Kaggle, `ealtman2019`). This script checks the file
size, records its SHA-256 and writes `SOURCE.json` next to it (a copy is committed as
`ml/aml/SOURCE.json`). The data file itself is not committed.

Citation: Altman, Blanusa, von Niederhaeusern, Egressy, Luksic and Bitar, "Realistic Synthetic
Financial Transactions for Anti-Money Laundering Models", NeurIPS 2023 (Datasets and Benchmarks).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

EXTERNAL = Path(__file__).resolve().parent / "data" / "external"
EXPECTED_BYTES = 475_664_283  # the size the Hugging Face file listing gives
URL = "https://huggingface.co/datasets/OsamaMIT/IBM-AML-HI-Small/resolve/main/HI-Small_Trans.csv"


def main() -> None:
    path = EXTERNAL / "HI-Small_Trans.csv"
    size = path.stat().st_size
    if size != EXPECTED_BYTES:
        raise SystemExit(
            f"{path.name} is {size:,} bytes, expected {EXPECTED_BYTES:,}: re-run curl -C -"
        )
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    source = {
        "dataset": "IBM Transactions for Anti Money Laundering (AML), HI-Small",
        "licence": "CDLA-Sharing-1.0",
        "downloaded_from": URL,
        "original": "https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml",
        "file": path.name,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "synthetic": True,
        "citation": "Altman et al., Realistic Synthetic Financial Transactions for Anti-Money "
        "Laundering Models, NeurIPS 2023 Datasets and Benchmarks",
    }
    (EXTERNAL / "SOURCE.json").write_text(
        json.dumps(source, indent=2), encoding="utf-8"
    )
    print(json.dumps(source, indent=2))


if __name__ == "__main__":
    main()
