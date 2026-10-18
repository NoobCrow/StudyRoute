from app.ai.masking import Masker

IBAN = "GB08EXMP12345612344821"


def test_names_become_numbered_tokens_and_come_back() -> None:
    masker = Masker(["Rahim Demo", "Karim Sample"])
    masked = masker.mask("Rahim Demo pays for Karim Sample. rahim demo again.")
    assert "Rahim" not in masked and "Karim" not in masked
    assert masked == "[PERSON_1] pays for [PERSON_2]. [PERSON_1] again."
    assert masker.unmask(masked) == "Rahim Demo pays for Karim Sample. Rahim Demo again."


def test_accounts_show_country_and_last_four_only() -> None:
    masker = Masker()
    masked = masker.mask(f"Send to {IBAN} or GB08 EXMP 1234 5612 3448 21 please")
    assert "EXMP" not in masked and "12344821" not in masked
    assert masked.count("[ACCT_") == 2
    assert masker.unmask(masked) == "Send to GB** **** 4821 or GB** **** 4821 please"


def test_long_account_numbers_and_cards_are_masked() -> None:
    masker = Masker()
    masked = masker.mask("account 12345678901234 and card 4111 1111 1111 1111")
    assert "1234567890" not in masked and "4111" not in masked
    assert masker.unmask(masked) == "account **** 1234 and card **** 1111"


def test_passports_emails_and_phones_are_removed_never_restored() -> None:
    masker = Masker()
    masked = masker.mask("Passport A1234567, mail mum@example.test, call +880 1712 345678")
    assert "A1234567" not in masked
    assert "mum@example.test" not in masked
    assert "1712" not in masked
    assert "[ID_REMOVED]" in masked and "[EMAIL_REMOVED]" in masked and "[PHONE_REMOVED]" in masked
    assert masker.unmask(masked) == masked


def test_amounts_dates_and_ids_are_left_alone() -> None:
    text = "Provider B costs 1.58%, BDT 1,625,300.00, due 2026-10-28, pay_01HZXA"
    assert Masker().mask(text) == text


def test_short_names_are_not_masked_to_avoid_mangling_words() -> None:
    assert Masker(["Al"]).mask("Alice and Al") == "Alice and Al"
