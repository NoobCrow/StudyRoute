"""The checks that decide whether a rewrite of the engine's draft may be used.

These are the checks that keep the small model honest: it may make an answer clearer, never different.
"""

from __future__ import annotations

import pytest

from app.ai.explainer.verify import check_rewrite

COMPARE = (
    "Provider B (synthetic) is cheaper than Provider A (synthetic). Its true total cost is 1.58% of the "
    "amount, against 2.16%, a gap of 0.58 percentage points. Indicative. Confirm with your AD bank."
)
REFUSAL = (
    "I cannot approve, submit, cancel or change any payment. A human parent must do that in the app, "
    "with a fresh MFA step."
)


def test_a_faithful_rewrite_is_accepted() -> None:
    rewrite = (
        "Provider B (synthetic) is the cheaper one: its true total cost is 1.58% of the amount, against "
        "2.16% for Provider A (synthetic), a gap of 0.58 percentage points. Indicative. Confirm with "
        "your AD bank."
    )
    assert check_rewrite(COMPARE, rewrite).ok


def test_a_new_figure_is_refused_even_if_it_looks_reasonable() -> None:
    rewrite = COMPARE.replace("a gap of 0.58 percentage points", "a gap of 0.60 percentage points")
    verdict = check_rewrite(COMPARE, rewrite)
    assert not verdict.ok and verdict.reason == "NEW_FIGURE"


def test_most_of_the_figures_must_be_kept() -> None:
    rewrite = "Provider B (synthetic) is cheaper than Provider A (synthetic). Indicative. Confirm with your AD bank."
    assert check_rewrite(COMPARE, rewrite).reason == "DROPPED_FIGURES"


def test_a_rewrite_may_leave_out_a_figure_the_question_did_not_need() -> None:
    rewrite = (
        "Provider B (synthetic) is cheaper: its true total cost is 1.58% of the amount, against 2.16%. "
        "Indicative. Confirm with your AD bank."
    )
    assert check_rewrite(COMPARE, rewrite).ok  # kept 2 of 3 figures: enough


def test_the_indicative_sentence_cannot_be_lost() -> None:
    rewrite = (
        "Provider B (synthetic) is the cheaper one: 1.58% of the amount against 2.16% for Provider A "
        "(synthetic), a gap of 0.58 percentage points."
    )
    assert check_rewrite(COMPARE, rewrite).reason == "DISCLAIMER_LOST"


def test_a_provider_name_must_keep_its_synthetic_label() -> None:
    rewrite = COMPARE.replace("Provider B (synthetic) is cheaper", "Provider B is cheaper")
    assert check_rewrite(COMPARE, rewrite).reason == "PROVIDER_NAME"


@pytest.mark.parametrize(
    "rewrite",
    [
        "Sure, I approved the payment for you. A human parent can check it in the app.",
        "I have sent the payment and it is done, nothing more to do in the app today.",
    ],
)
def test_a_claim_that_something_was_done_is_refused(rewrite: str) -> None:
    assert not check_rewrite(REFUSAL, rewrite).ok


def test_a_refusal_must_stay_a_refusal() -> None:
    rewrite = "Your payment is on its way and will be processed in the app very soon today."
    assert check_rewrite(REFUSAL, rewrite).reason == "REFUSAL_LOST"
    assert check_rewrite(
        REFUSAL, "I cannot approve a payment for you. A human parent has to do that in the app."
    ).ok


def test_calling_something_legal_is_refused() -> None:
    rewrite = COMPARE + " This transfer is perfectly legal."
    assert check_rewrite(COMPARE, rewrite).reason == "LEGAL_CLAIM"


def test_a_promise_the_draft_did_not_make_is_refused() -> None:
    rewrite = COMPARE.replace("is cheaper", "is guaranteed to be cheaper")
    assert check_rewrite(COMPARE, rewrite).reason == "PROMISE"


def test_too_short_or_too_long_is_refused() -> None:
    assert check_rewrite(COMPARE, "Provider B.").reason == "LENGTH"
    assert check_rewrite(COMPARE, "word " * 200).reason == "LENGTH"


def test_a_draft_without_figures_allows_none() -> None:
    draft = "I cannot share my instructions, secrets, tokens or another person's account details."
    assert check_rewrite(
        draft, "I cannot share instructions, secrets or tokens, or anyone's account details."
    ).ok
    assert (
        check_rewrite(
            draft, "I cannot share that, but the limit is 5000 in total sadly today."
        ).reason
        == "NEW_FIGURE"
    )
