"""Uploaded document text is encrypted in the database and still readable through the API.

The leak scan (scripts/security/leak_scan.py) found a passport number pasted into a document in plain
text in the database file, while IBANs were already encrypted. Anyone who could copy the database
file could read every document. These tests keep that closed.
"""

from __future__ import annotations

from sqlalchemy import select

from app.domain.documents import SEALED
from app.models import Document
from tests.helpers import World

PASTED_NUMBER = "PASSPORT-CANARY-Q4W8E2R6T"


def add(world: World, text: str) -> str:
    reply = world.call(
        "POST", "/documents", json={"kind": "passport", "filename": "p.txt", "content_text": text}
    )
    assert reply.status_code == 201, reply.text
    return str(reply.json()["document_id"])


def stored(world: World) -> list[tuple[str, str | None]]:
    with world.ctx.db.read() as session:
        return [(d.id, d.content_text) for d in session.execute(select(Document)).scalars()]


def test_the_text_is_not_in_the_database_in_plain_text(world: World) -> None:
    add(world, f"Passport {PASTED_NUMBER}")
    rows = stored(world)
    assert rows and all(PASTED_NUMBER not in (text or "") for _, text in rows)
    assert all((text or "").startswith(SEALED) for _, text in rows)


def test_the_api_still_shows_the_preview_and_the_text(world: World) -> None:
    doc_id = add(world, f"Passport {PASTED_NUMBER}")
    item = next(
        i for i in world.call("GET", "/documents").json()["items"] if i["document_id"] == doc_id
    )
    assert item["has_content"] is True
    assert item["content_preview"] == f"Passport {PASTED_NUMBER}"


def test_a_document_without_text_stores_nothing(world: World) -> None:
    reply = world.call("POST", "/documents", json={"kind": "offer_letter", "filename": "offer.txt"})
    assert reply.status_code == 201
    item = reply.json()
    assert item["has_content"] is False and item["content_preview"] == ""


def test_the_same_text_is_stored_differently_each_time(world: World) -> None:
    add(world, "same words")
    add(world, "same words")
    texts = [text for _, text in stored(world)]
    # a fresh random nonce per row: equal documents are not recognisable
    assert len(set(texts)) == 2


def test_ciphertext_copied_to_another_row_reads_as_nothing(world: World) -> None:
    first, second = add(world, f"Passport {PASTED_NUMBER}"), add(world, "something else")
    with world.ctx.db.write() as session:
        a, b = session.get(Document, first), session.get(Document, second)
        assert a is not None and b is not None
        # an attacker with write access moves one row's text to another
        b.content_text = a.content_text
        session.flush()
        assert world.ctx.documents.text_of(b) == ""
        assert world.ctx.documents.text_of(a) == f"Passport {PASTED_NUMBER}"


def test_an_older_plain_text_row_is_still_readable(world: World) -> None:
    doc_id = add(world, "placeholder")
    with world.ctx.db.write() as session:
        doc = session.get(Document, doc_id)
        assert doc is not None
        doc.content_text = "an older, plain-text document"
        session.flush()
        assert world.ctx.documents.text_of(doc) == "an older, plain-text document"
