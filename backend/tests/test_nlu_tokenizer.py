"""The tokenizer used both to train the reader and to run it, so the two cannot disagree."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.nlu.runtime import MODEL_DIR
from app.ai.nlu.schema import INTENTS, MAX_PIECES, SLOTS, TAGS
from app.ai.nlu.tokenizer import WordPiece, split_words

VOCAB = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "pay", "##ing", "gbp", "10", "k", "£", ",", "000", "i"]


def test_words_keep_their_place_in_the_original_text() -> None:
    message = "I need £10,000 by 28th Oct, gbp10000 10k!"
    words = split_words(message)
    assert [w.text for w in words][:8] == ["i", "need", "£", "10", ",", "000", "by", "28"]
    for word in words:
        assert message[word.start : word.end].lower().replace("£", "£") == word.text


def test_a_value_and_its_unit_are_separate_words() -> None:
    assert [w.text for w in split_words("gbp10000")] == ["gbp", "10000"]
    assert [w.text for w in split_words("10k")] == ["10", "k"]
    assert [w.text for w in split_words("28th")] == ["28", "th"]


def test_accents_and_control_characters_do_not_move_offsets() -> None:
    message = "Café\tpay​ now"
    words = split_words(message)
    assert [w.text for w in words] == ["cafe", "pay", "now"]
    assert message[words[0].start : words[0].end] == "Café"
    assert message[words[2].start : words[2].end] == "now"


def test_wordpiece_splits_greedily_and_marks_unknown_words() -> None:
    tokenizer = WordPiece(VOCAB)
    assert tokenizer.pieces("paying") == [VOCAB.index("pay"), VOCAB.index("##ing")]
    assert tokenizer.pieces("zzz") == [tokenizer.unk_id]
    assert tokenizer.pieces("x" * 200) == [tokenizer.unk_id]


def test_encoding_adds_markers_and_maps_each_word_to_its_first_piece() -> None:
    tokenizer = WordPiece(VOCAB)
    encoding = tokenizer.encode("I paying GBP 10k")
    assert encoding.ids[0] == tokenizer.cls_id and encoding.ids[-1] == tokenizer.sep_id
    assert [w.text for w in encoding.words] == ["i", "paying", "gbp", "10", "k"]
    assert [encoding.ids[i] for i in encoding.first_piece] == [
        VOCAB.index("i"), VOCAB.index("pay"), VOCAB.index("gbp"), VOCAB.index("10"), VOCAB.index("k")
    ]  # fmt: skip


def test_a_long_message_is_cut_at_a_word_boundary() -> None:
    tokenizer = WordPiece(VOCAB)
    encoding = tokenizer.encode("pay " * 500)
    assert len(encoding.ids) <= MAX_PIECES
    assert len(encoding.words) == len(encoding.first_piece)
    assert encoding.ids[-1] == tokenizer.sep_id


def test_a_vocabulary_without_the_special_tokens_is_refused() -> None:
    with pytest.raises(ValueError, match="CLS"):
        WordPiece(["a", "b"])


def test_the_shipped_vocabulary_loads_and_knows_the_special_tokens() -> None:
    vocab = MODEL_DIR / "vocab.txt"
    if not Path(vocab).is_file():
        pytest.skip("the model files are not present")
    tokenizer = WordPiece.from_file(vocab)
    encoding = tokenizer.encode("I need to pay GBP 10,000 tuition by 28 October")
    assert tokenizer.unk_id not in encoding.ids


def test_labels_are_consistent() -> None:
    assert len(INTENTS) == len(set(INTENTS)) and "ATTACK" in INTENTS and "OUT_OF_SCOPE" in INTENTS
    assert TAGS[0] == "O" and len(TAGS) == 1 + 2 * len(SLOTS)


def test_the_reader_switches_off_onnx_runtime_telemetry() -> None:
    """The library phones home to Microsoft on Linux by default; StudyRoute promises no tracking."""
    import os

    import app.ai.nlu.runtime  # noqa: F401  (importing it sets the variable)

    assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"
