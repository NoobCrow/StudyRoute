from datetime import date

from app.engine.money import Money
from app.engine.mt103 import UETR_PENDING, build_instruction_preview, mt_amount
from app.engine.quote import ChargeCode


def preview(**overrides):
    args = {
        "payment_id": "pay_TEST",
        "uetr": None,
        "value_date": date(2026, 10, 28),
        "amount": Money(1_000_000, "GBP"),
        "ordering_name": "Parent Demo",
        "ordering_address": "Dhaka, BD (synthetic)",
        "receiving_bic": "EXMPGB2L",
        "beneficiary_name": "University of Example (synthetic)",
        "beneficiary_account_masked": "GB** **** 4821",
        "remittance": "INV-2026-4471 / STU-883201",
        "charge_code": ChargeCode.OUR,
    }
    args.update(overrides)
    return build_instruction_preview(**args)


def fields(body):
    return {f["tag"]: f["value"] for f in body["fields"]}


def test_mt_amount_uses_a_decimal_comma() -> None:
    assert mt_amount(Money(1_000_000, "GBP")) == "10000,00"
    assert mt_amount(Money(5, "USD")) == "0,05"
    assert mt_amount(Money(1500, "JPY")) == "1500,"


def test_preview_contains_every_blueprint_field() -> None:
    body = fields(preview())
    assert set(body) == {
        "{121:}",
        ":20:",
        ":23B:",
        ":32A:",
        ":50K:",
        ":57A:",
        ":59:",
        ":70:",
        ":71A:",
    }
    assert body[":32A:"] == "261028GBP10000,00"
    assert body[":71A:"] == "OUR"
    assert body["{121:}"] == UETR_PENDING


def test_account_is_masked_and_travel_rule_data_is_present() -> None:
    body = fields(preview())
    assert "4821" in body[":59:"]
    assert "WEST" not in body[":59:"]
    assert "Parent Demo" in body[":50K:"]
    assert "University of Example" in body[":59:"]


def test_charge_code_maps_to_iso_20022_bearer() -> None:
    for code, bearer in (
        (ChargeCode.OUR, "DEBT"),
        (ChargeCode.SHA, "SHAR"),
        (ChargeCode.BEN, "CRED"),
    ):
        assert preview(charge_code=code)["pacs008"]["ChrgBr"] == bearer


def test_uetr_is_shown_once_assigned_and_preview_is_labelled_simulated() -> None:
    body = preview(uetr="7c1d4f0e-5a9b-4e3c-8a21-2b6f9d0c1e44")
    assert fields(body)["{121:}"] == "7c1d4f0e-5a9b-4e3c-8a21-2b6f9d0c1e44"
    assert body["simulated"] is True
    assert any("Simulated" in note for note in body["notes"])
