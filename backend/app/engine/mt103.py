"""Payment instruction preview: MT103 fields and the pacs.008 equivalents (blueprint 5.2).

Shows the originator and beneficiary data that travels with a cross-border payment (FATF
Recommendation 16, the "travel rule"). Everything here is a SIMULATED message preview.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.engine.money import Money, exponent
from app.engine.quote import CHARGE_BEARER, ChargeCode

UETR_PENDING = "(assigned when the instruction is submitted)"
VALUE_DATE_PENDING = "(assigned by the bank)"


def mt_amount(amount: Money) -> str:
    """SWIFT amount format: decimal comma, no thousands separator, e.g. 10000,00."""
    exp = exponent(amount.currency)
    major, minor = divmod(abs(amount.amount_minor), 10**exp)
    return f"{major},{minor:0{exp}d}" if exp else f"{major},"


def build_instruction_preview(
    *,
    payment_id: str,
    uetr: str | None,
    value_date: date | None,
    amount: Money,
    ordering_name: str,
    ordering_address: str,
    receiving_bic: str,
    beneficiary_name: str,
    beneficiary_account_masked: str,
    remittance: str,
    charge_code: ChargeCode,
) -> dict[str, Any]:
    value_text = (
        f"{value_date.strftime('%y%m%d')}{amount.currency}{mt_amount(amount)}"
        if value_date
        else f"{VALUE_DATE_PENDING} {amount.currency}{mt_amount(amount)}"
    )
    fields = [
        ("{121:}", "UETR (header)", uetr or UETR_PENDING, "Unique end-to-end transaction reference (UUID v4)."),
        (":20:", "Sender's reference", payment_id, "The sandbox shows the full payment id."),
        (":23B:", "Bank operation code", "CRED", "Customer credit transfer."),
        (":32A:", "Value date, currency, amount", value_text, "Value date is the due date you entered."),
        (":50K:", "Ordering customer", f"{ordering_name}\n{ordering_address}", "Originator data (travel rule). Masked in logs."),
        (":57A:", "Account with institution", receiving_bic, "Receiving bank BIC."),
        (":59:", "Beneficiary customer", f"{beneficiary_account_masked}\n{beneficiary_name}", "Beneficiary data (travel rule). Account masked."),
        (":70:", "Remittance information", remittance, "The university uses this to match the payment."),
        (":71A:", "Details of charges", charge_code.value, "OUR, SHA or BEN."),
    ]  # fmt: skip
    return {
        "format": "MT103",
        "simulated": True,
        "fields": [
            {"tag": tag, "name": name, "value": value, "note": note}
            for tag, name, value, note in fields
        ],
        "pacs008": {
            "ChrgBr": CHARGE_BEARER[charge_code],
            "UETR": uetr,
            "InstdAmt": {
                "currency": amount.currency,
                "amount": mt_amount(amount).replace(",", "."),
            },
            "RmtInf": remittance,
        },
        "notes": [
            "Simulated message preview. No SWIFT message is sent and no money moves.",
            "A purpose code is not shown: check the ISO 20022 external code list first.",
        ],
    }
