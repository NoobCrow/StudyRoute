"""Format validators for payment identifiers (blueprint 5.2). Pure functions."""

from __future__ import annotations

import re
import uuid

# IBAN length per country (ISO 13616 registry). Countries not listed are rejected.
IBAN_LENGTHS: dict[str, int] = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22,
    "BH": 22, "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22,
    "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18, "FO": 18, "FR": 27,
    "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HR": 21, "HU": 28,
    "IE": 22, "IL": 23, "IQ": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20,
    "LB": 28, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MD": 24, "ME": 22,
    "MK": 19, "MR": 27, "MT": 31, "MU": 30, "NL": 18, "NO": 15, "PK": 24, "PL": 28,
    "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22, "SA": 24, "SE": 24, "SI": 19,
    "SK": 24, "SM": 27, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
}  # fmt: skip

_IBAN_SHAPE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_BIC = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
_UETR = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_SWIFT_REFERENCE = re.compile(r"^[A-Za-z0-9/\-?:().,'+ ]{1,140}$")
_ABA_WEIGHTS = (3, 7, 1, 3, 7, 1, 3, 7, 1)


def normalize_iban(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def is_valid_iban(value: str) -> bool:
    """ISO 13616: shape, registry length, then the mod-97 check must equal 1."""
    iban = normalize_iban(value)
    if not _IBAN_SHAPE.match(iban):
        return False
    if IBAN_LENGTHS.get(iban[:2]) != len(iban):
        return False
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(char, 36)) for char in rearranged)
    return int(digits) % 97 == 1


def is_valid_bic(value: str) -> bool:
    return bool(_BIC.match(value.strip().upper()))


def _digits_only(value: str) -> str:
    return re.sub(r"[\s-]", "", value)


def is_valid_uk_sort_code(value: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", _digits_only(value)))


def is_valid_uk_account(value: str) -> bool:
    return bool(re.fullmatch(r"\d{8}", _digits_only(value)))


def is_valid_aba(value: str) -> bool:
    """US routing number: nine digits and a 3-7-1 weighted checksum divisible by 10."""
    digits = _digits_only(value)
    if not re.fullmatch(r"\d{9}", digits):
        return False
    return sum(int(d) * w for d, w in zip(digits, _ABA_WEIGHTS, strict=True)) % 10 == 0


def is_valid_uetr(value: str) -> bool:
    return bool(_UETR.match(value))


def new_uetr() -> str:
    return str(uuid.uuid4())


def is_valid_swift_reference(value: str) -> bool:
    """Characters allowed in MT103 field :70: and at most 4 x 35 characters."""
    return bool(_SWIFT_REFERENCE.match(value))


def last4(value: str) -> str:
    alnum = re.sub(r"[^A-Za-z0-9]", "", value)
    return alnum[-4:]


def mask_account(value: str, country: str) -> str:
    """Show the country and the last four characters only, e.g. GB** **** 5432."""
    return f"{country.upper()}** **** {last4(value)}"
