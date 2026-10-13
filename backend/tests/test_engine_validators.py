"""IBAN mod-97, BIC, UK sort code and account, US ABA and UETR validators (blueprint 5.2)."""

import pytest

from app.engine import validators as v

# Well-known documentation examples and synthetic numbers. None is a real account.
VALID_IBANS = [
    "GB82WEST12345698765432",
    "DE89370400440532013000",
    "FR1420041010050500013M02606",
    "NL91ABNA0417164300",
    "GB82 WEST 1234 5698 7654 32",
    "gb82west12345698765432",
]


@pytest.mark.parametrize("iban", VALID_IBANS)
def test_valid_ibans_pass(iban: str) -> None:
    assert v.is_valid_iban(iban)


def test_T03_one_changed_digit_fails_the_checksum() -> None:
    assert not v.is_valid_iban("GB82WEST12345698765433")
    assert not v.is_valid_iban("GB82WEST12345698765332")
    assert not v.is_valid_iban("GB83WEST12345698765432")


@pytest.mark.parametrize(
    "iban",
    ["", "GB82", "GB82WEST1234569876543", "XX0012345678901234", "GB82WEST1234569876543!", "1234"],
)
def test_malformed_ibans_fail(iban: str) -> None:
    assert not v.is_valid_iban(iban)


def test_normalize_iban_removes_spaces_and_uppercases() -> None:
    assert v.normalize_iban(" gb82 west 1234 5698 7654 32 ") == "GB82WEST12345698765432"


@pytest.mark.parametrize("bic", ["NWBKGB2L", "NWBKGB2LXXX", "DEUTDEFF500", "abcdgb2l"])
def test_valid_bics(bic: str) -> None:
    assert v.is_valid_bic(bic)


@pytest.mark.parametrize(
    "bic", ["NWBKGB2", "12BKGB2L", "NWBKGB2LX", "NWBK-B2L", "", "NWBKGB2LXXXX"]
)
def test_invalid_bics(bic: str) -> None:
    assert not v.is_valid_bic(bic)


def test_uk_sort_code_and_account() -> None:
    assert v.is_valid_uk_sort_code("123456")
    assert v.is_valid_uk_sort_code("12-34-56")
    assert not v.is_valid_uk_sort_code("12345")
    assert not v.is_valid_uk_sort_code("12345a")
    assert v.is_valid_uk_account("12345678")
    assert not v.is_valid_uk_account("1234567")
    assert not v.is_valid_uk_account("123456789")


def test_us_aba_checksum() -> None:
    assert v.is_valid_aba("123456780")
    assert not v.is_valid_aba("123456789")
    assert not v.is_valid_aba("12345678")
    assert not v.is_valid_aba("12345678a")


def test_uetr_must_be_a_version_4_uuid() -> None:
    assert v.is_valid_uetr("7c1d4f0e-5a9b-4e3c-8a21-2b6f9d0c1e44")
    assert not v.is_valid_uetr("7c1d4f0e-5a9b-1e3c-8a21-2b6f9d0c1e44")
    assert not v.is_valid_uetr("7c1d4f0e-5a9b-4e3c-1a21-2b6f9d0c1e44")
    assert not v.is_valid_uetr("not-a-uuid")


def test_new_uetr_is_valid() -> None:
    assert v.is_valid_uetr(v.new_uetr())
    assert v.new_uetr() != v.new_uetr()


def test_swift_reference_charset() -> None:
    assert v.is_valid_swift_reference("INV-2026-4471 / STU-883201")
    assert not v.is_valid_swift_reference("bad_underscore")
    assert not v.is_valid_swift_reference("<script>")
    assert not v.is_valid_swift_reference("")
    assert not v.is_valid_swift_reference("x" * 141)


def test_mask_account_keeps_country_and_last_four_only() -> None:
    assert v.mask_account("GB82WEST12345698765432", "GB") == "GB** **** 5432"
    assert v.mask_account("12345678", "US") == "US** **** 5678"
    assert "WEST" not in v.mask_account("GB82WEST12345698765432", "GB")


def test_iban_country_length_table_covers_supported_corridors() -> None:
    for country in ("GB", "DE", "FR", "IE", "NL", "ES", "IT"):
        assert country in v.IBAN_LENGTHS
