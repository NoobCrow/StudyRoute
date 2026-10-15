"""Turning the model's per-word tags into spans of the original message."""

from __future__ import annotations

from app.ai.nlu.runtime import Reader
from app.ai.nlu.schema import TAG_ID
from app.ai.nlu.tokenizer import Encoding, Word, split_words


def decode(message: str, tags: list[str]):  # type: ignore[no-untyped-def]
    words = split_words(message)
    assert len(words) == len(tags), [w.text for w in words]
    encoding = Encoding([0] * len(words), words, list(range(len(words))))
    ids = [TAG_ID[t] for t in tags]
    return Reader._spans(message, encoding, ids, [0.9] * len(ids))


def test_contiguous_tags_become_one_span_cut_from_the_original_text() -> None:
    spans, confidences = decode(
        "pay GBP 10,000 by 28 October",
        ["O", "B-CURRENCY", "B-AMOUNT", "I-AMOUNT", "I-AMOUNT", "O", "B-DATE", "I-DATE"],
    )
    assert [(s.label, s.text) for s in spans] == [
        ("CURRENCY", "GBP"),
        ("AMOUNT", "10,000"),
        ("DATE", "28 October"),
    ]
    assert len(confidences) == 3


def test_an_inside_tag_with_no_start_still_opens_a_span() -> None:
    spans, _ = decode("fees due tomorrow", ["O", "O", "I-DATE"])
    assert [(s.label, s.text) for s in spans] == [("DATE", "tomorrow")]


def test_two_different_labels_side_by_side_stay_separate() -> None:
    spans, _ = decode("£10", ["B-CURRENCY", "B-AMOUNT"])
    assert [(s.label, s.text) for s in spans] == [("CURRENCY", "£"), ("AMOUNT", "10")]


def test_an_amount_cut_at_its_separator_is_put_back_together() -> None:
    spans, confidences = decode("GBP 10,000", ["B-CURRENCY", "B-AMOUNT", "O", "B-AMOUNT"])
    assert [(s.label, s.text) for s in spans] == [("CURRENCY", "GBP"), ("AMOUNT", "10,000")]
    assert len(confidences) == 2


def test_two_separate_amounts_are_not_merged() -> None:
    spans, _ = decode("800 and 7200", ["B-AMOUNT", "O", "B-AMOUNT"])
    assert [s.text for s in spans] == ["800", "7200"]
    spans, _ = decode("800 then 900", ["B-AMOUNT", "O", "B-AMOUNT"])
    assert len(spans) == 2


def test_a_message_with_no_slots_has_no_spans() -> None:
    spans, confidences = decode("hello there", ["O", "O"])
    assert spans == [] and confidences == []


def test_word_offsets_stay_inside_the_message() -> None:
    word = Word("x", 0, 1)
    assert word.end - word.start == 1
