"""A WordPiece tokenizer that remembers where every word sits in the original message.

The reader model is a small BERT-style network, so it needs WordPiece ids. This module is the
only tokenizer used, both when the model is trained and when it runs in the API, so the two can
never disagree. It has no dependencies: the vocabulary is a plain text file shipped with the model.

Words are split so that a value and its unit are separate words ("gbp10000" is "gbp" and "10000",
"10k" is "10" and "k", "£10,000" is "£", "10", ",", "000"). That lets the model label them
separately. Every word keeps its character range, so a predicted span can be cut out of the
message as the person wrote it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.ai.nlu.schema import MAX_PIECES

CLS, SEP, PAD, UNK = "[CLS]", "[SEP]", "[PAD]", "[UNK]"
MAX_WORD_CHARS = 100
_WORD = re.compile(r"[^\W\d_]+|\d+|[^\w\s]|_")


@dataclass(frozen=True)
class Word:
    text: str  # lower-cased, as the model sees it
    start: int  # character range in the original message
    end: int


@dataclass(frozen=True)
class Encoding:
    ids: list[int]  # [CLS] pieces [SEP]
    words: list[Word]
    first_piece: list[int]  # for each word, the index of its first piece in ids


def split_words(message: str) -> list[Word]:
    """Lower-case, drop accents and split into words, keeping offsets into ``message``."""
    chars: list[str] = []
    origin: list[int] = []  # the index in ``message`` each kept character came from
    for index, char in enumerate(message):
        for part in unicodedata.normalize("NFD", char.lower()):
            if part.isspace():
                chars.append(" ")
            elif unicodedata.category(part) == "Mn" or unicodedata.category(part).startswith("C"):
                continue  # accents and control characters carry no meaning for the reader
            else:
                chars.append(part)
            origin.append(index)
    lowered = "".join(chars)
    words: list[Word] = []
    for match in _WORD.finditer(lowered):
        start = origin[match.start()]
        end = origin[match.end() - 1] + 1
        words.append(Word(match.group(), start, end))
    return words


class WordPiece:
    def __init__(self, vocab: list[str]) -> None:
        self._index = {token: i for i, token in enumerate(vocab)}
        for special in (CLS, SEP, PAD, UNK):
            if special not in self._index:
                raise ValueError(f"vocabulary has no {special}")
        self.cls_id = self._index[CLS]
        self.sep_id = self._index[SEP]
        self.pad_id = self._index[PAD]
        self.unk_id = self._index[UNK]

    @classmethod
    def from_file(cls, path: Path) -> WordPiece:
        return cls(path.read_text(encoding="utf-8").splitlines())

    def pieces(self, word: str) -> list[int]:
        """Greedy longest-match-first, the standard WordPiece rule."""
        if len(word) > MAX_WORD_CHARS:
            return [self.unk_id]
        found: list[int] = []
        start = 0
        while start < len(word):
            end = len(word)
            match: int | None = None
            while start < end:
                piece = word[start:end] if start == 0 else "##" + word[start:end]
                if piece in self._index:
                    match = self._index[piece]
                    break
                end -= 1
            if match is None:
                return [self.unk_id]
            found.append(match)
            start = end
        return found

    def encode(self, message: str, max_pieces: int = MAX_PIECES) -> Encoding:
        ids = [self.cls_id]
        words: list[Word] = []
        first_piece: list[int] = []
        for word in split_words(message):
            pieces = self.pieces(word.text)
            if len(ids) + len(pieces) > max_pieces - 1:  # keep room for [SEP]
                break
            first_piece.append(len(ids))
            words.append(word)
            ids.extend(pieces)
        ids.append(self.sep_id)
        return Encoding(ids, words, first_piece)
