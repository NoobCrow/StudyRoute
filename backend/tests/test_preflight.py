"""scripts/preflight.py and scripts/personalize.py: the final-readiness tools for the submission."""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


preflight = load("preflight")
personalize = load("personalize")


def make_deck(path: Path, slides: int, notes: int, text: str = "Hello") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for number in range(1, slides + 1):
            archive.writestr(f"ppt/slides/slide{number}.xml", f"<p><a:t>{text} {number}</a:t></p>")
        for number in range(1, notes + 1):
            archive.writestr(
                f"ppt/notesSlides/notesSlide{number}.xml", f"<p><a:t>note {number}</a:t></p>"
            )


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- deadline ----------------------------------------------------------------------------------


def test_the_deadline_check_counts_down_in_beijing_time() -> None:
    check = preflight.deadline_check(datetime(2026, 10, 14, 12, 0, tzinfo=UTC))
    assert check.status == preflight.INFO
    assert "20 Oct 2026 23:59 Beijing (21:59 Dhaka)" in check.detail and "days" in check.detail


def test_after_the_deadline_the_check_fails() -> None:
    check = preflight.deadline_check(datetime(2026, 10, 20, 16, 0, tzinfo=UTC))  # 00:00 on the 21st
    assert check.status == preflight.FAIL


def test_the_deadline_is_exactly_23_59_beijing_which_is_21_59_dhaka() -> None:
    assert preflight.DEADLINE.astimezone(preflight.DHAKA).strftime("%H:%M") == "21:59"
    assert preflight.DEADLINE.astimezone(UTC).strftime("%d %H:%M") == "20 15:59"


def test_once_the_internal_target_has_passed_it_says_submit_now() -> None:
    check = preflight.deadline_check(datetime(2026, 10, 19, 15, 0, tzinfo=UTC))  # 21:00 in Dhaka
    assert check.status == preflight.INFO and "submit now" in check.detail


# --- the deck and the placeholders --------------------------------------------------------------


def test_the_deck_text_includes_slides_and_speaker_notes(tmp_path: Path) -> None:
    deck = tmp_path / "deck.pptx"
    make_deck(deck, 2, 2, "[Team name]")
    text = preflight.deck_text(deck)
    assert "[Team name] 1" in text and "note 2" in text


@pytest.mark.parametrize(
    ("slides", "notes", "status"), [(20, 20, "OK"), (19, 20, "FAIL"), (20, 0, "FAIL")]
)
def test_the_deck_must_have_twenty_slides_with_notes(
    tmp_path: Path, slides: int, notes: int, status: str
) -> None:
    (tmp_path / "submission").mkdir()
    make_deck(tmp_path / "submission" / "StudyRoute_Deck.pptx", slides, notes)
    assert preflight.deck_check(tmp_path).status == status


def test_speaker_notes_that_run_past_ten_minutes_fail(tmp_path: Path) -> None:
    (tmp_path / "submission").mkdir()
    deck = tmp_path / "submission" / "StudyRoute_Deck.pptx"
    with zipfile.ZipFile(deck, "w") as archive:
        for number in range(1, 21):
            archive.writestr(f"ppt/slides/slide{number}.xml", f"<p><a:t>Slide {number}</a:t></p>")
            words = "word " * 80  # 20 x 80 = 1,600 words: about 11 minutes at 150 a minute
            archive.writestr(
                f"ppt/notesSlides/notesSlide{number}.xml", f"<p><a:t>{words}</a:t></p>"
            )
    check = preflight.deck_check(tmp_path)
    assert check.status == "FAIL" and "minutes" in check.detail


def test_a_missing_or_broken_deck_fails(tmp_path: Path) -> None:
    assert preflight.deck_check(tmp_path).status == preflight.FAIL
    write(tmp_path, "submission/StudyRoute_Deck.pptx", "not a zip")
    assert preflight.deck_check(tmp_path).status == preflight.FAIL


def test_placeholders_are_found_in_the_documents_and_the_deck(tmp_path: Path) -> None:
    write(
        tmp_path, "submission/PROJECT_DESCRIPTION.md", "Team: [team name]. See [repository link]."
    )
    write(tmp_path, "submission/DECK_OUTLINE.md", "Clean file")
    make_deck(tmp_path / "submission" / "StudyRoute_Deck.pptx", 1, 1, "[Team name]")
    found = preflight.find_placeholders(tmp_path)
    assert found["[team name]"] == ["submission/PROJECT_DESCRIPTION.md"]
    assert found["[repository link]"] == ["submission/PROJECT_DESCRIPTION.md"]
    assert found["[Team name]"] == ["submission/StudyRoute_Deck.pptx"]
    assert preflight.placeholder_check(tmp_path).status == preflight.OPEN


def test_nothing_is_reported_once_everything_is_filled_in(tmp_path: Path) -> None:
    write(tmp_path, "submission/PROJECT_DESCRIPTION.md", "Team: Alpha. See https://github.com/a/b.")
    make_deck(tmp_path / "submission" / "StudyRoute_Deck.pptx", 1, 1, "Alpha")
    assert preflight.placeholder_check(tmp_path).status == preflight.OK


def test_send_time_brackets_in_the_e_mail_template_are_not_placeholders(tmp_path: Path) -> None:
    write(tmp_path, "submission/EMAIL_TEMPLATES.md", "To [Country], with [link] and [file or link]")
    assert preflight.find_placeholders(tmp_path) == {}


# --- evidence and deliverables ------------------------------------------------------------------


def evidence(
    root: Path, *, chain: str = "PASS", log: str = "      OK   fine\n", bank_ok: bool = True
) -> None:
    write(root, "submission/evidence/audit_verify.json", json.dumps({"status": chain}))
    write(root, "submission/evidence/sandbox_operation_log.txt", log)
    write(
        root, "submission/evidence/bank_network.json", json.dumps({"network": {"all_ok": bank_ok}})
    )


def test_good_evidence_passes(tmp_path: Path) -> None:
    evidence(tmp_path)
    assert preflight.evidence_check(tmp_path).status == preflight.OK


@pytest.mark.parametrize(
    ("kwargs", "words"),
    [
        ({"chain": "FAIL"}, "audit chain"),
        ({"log": "      FAIL a check\n"}, "failed demo check"),
        ({"bank_ok": False}, "bank ledger"),
    ],
)
def test_broken_evidence_fails_and_says_why(
    tmp_path: Path, kwargs: dict[str, object], words: str
) -> None:
    evidence(tmp_path, **kwargs)  # type: ignore[arg-type]
    check = preflight.evidence_check(tmp_path)
    assert check.status == preflight.FAIL and words in check.detail


def test_missing_evidence_fails(tmp_path: Path) -> None:
    assert preflight.evidence_check(tmp_path).status == preflight.FAIL


def test_every_missing_deliverable_fails(tmp_path: Path) -> None:
    checks = preflight.deliverable_checks(tmp_path)
    assert len(checks) == len(preflight.DELIVERABLES)
    assert {c.status for c in checks} == {preflight.FAIL}


# --- the whole thing -----------------------------------------------------------------------------


def test_the_repository_itself_has_nothing_broken() -> None:
    checks = preflight.run_checks(ROOT, now=datetime(2026, 10, 14, 12, 0, tzinfo=UTC))
    broken = [f"{c.name}: {c.detail}" for c in checks if c.status == preflight.FAIL]
    assert broken == []
    names = {c.name for c in checks}
    assert {"secret scan", "execution evidence", "deck", "Docker", "demo video", "team"} <= names


def test_the_items_only_a_person_can_do_are_always_listed() -> None:
    names = {c.name for c in preflight.manual_checks()}
    assert names == {"team", "registration", "submission e-mail"}
    assert {c.status for c in preflight.manual_checks()} == {preflight.OPEN}


@pytest.mark.parametrize(
    ("statuses", "argv", "code"),
    [
        (["OK", "INFO"], [], 0),
        (["OK", "OPEN"], [], 0),
        (["OK", "OPEN"], ["--strict"], 1),
        (["OK", "FAIL", "OPEN"], [], 1),
        (["OK", "INFO"], ["--strict"], 0),
    ],
)
def test_the_exit_code_only_blocks_on_broken_things_unless_strict(
    monkeypatch: pytest.MonkeyPatch, statuses: list[str], argv: list[str], code: int
) -> None:
    fake = [preflight.Check(s, f"item {i}", "detail") for i, s in enumerate(statuses)]
    monkeypatch.setattr(preflight, "run_checks", lambda: fake)
    assert preflight.main(argv) == code


# --- personalize ---------------------------------------------------------------------------------


TEMPLATES = {
    "submission/PROJECT_DESCRIPTION.md": (
        "Team: [team name]. Members: [names and universities]. Code: [repository link]\n"
    ),
    "submission/DECK_OUTLINE.md": "Cover slide. Team: [Team name]. Code: [repository link]\n",
    "submission/EMAIL_TEMPLATES.md": (
        "Subject: [Country] - [Team name]\nGitHub: [repository link]\nArchive: [link]\n"
        "Kind regards, [team name]\n"
    ),
}


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    """Unpersonalised copies of the three documents, so the tests do not depend on the repository
    still holding placeholders (running `scripts/personalize.py` on the real files must not break them)."""
    for relative, text in TEMPLATES.items():
        write(tmp_path, relative, text)
    return tmp_path


def test_the_placeholders_are_replaced_and_send_time_brackets_are_left(docs: Path) -> None:
    counts = personalize.apply(
        docs, "Team Alpha", "https://github.com/alpha/studyroute", "A (U1), B (U2)"
    )
    assert all(count > 0 for count in counts.values())
    text = "\n".join((docs / f).read_text(encoding="utf-8") for f in personalize.FILES)
    for gone in ("[team name]", "[Team name]", "[repository link]", "[names and universities]"):
        assert gone not in text
    assert "Team Alpha" in text and "https://github.com/alpha/studyroute" in text
    assert "A (U1), B (U2)" in text
    assert "[Country]" in text and "[link]" in text  # for the person sending the e-mail


def test_running_it_twice_changes_nothing_the_second_time(docs: Path) -> None:
    personalize.apply(docs, "Team Alpha", "https://github.com/alpha/studyroute", None)
    assert set(personalize.apply(docs, "Other", "https://github.com/o/p", None).values()) == {0}


def test_members_stay_a_placeholder_when_not_given(docs: Path) -> None:
    personalize.apply(docs, "Team Alpha", "https://github.com/alpha/studyroute", None)
    text = (docs / "submission/PROJECT_DESCRIPTION.md").read_text(encoding="utf-8")
    assert "[names and universities]" in text


def test_personalising_clears_what_the_preflight_asked_for(docs: Path) -> None:
    assert preflight.find_placeholders(docs)
    personalize.apply(docs, "Team Alpha", "https://github.com/alpha/studyroute", "A (U1), B (U2)")
    assert preflight.find_placeholders(docs) == {}


@pytest.mark.parametrize("bad", ["", "   ", "x" * 81, "Team [A]", "Team|A", "Team`A", "Team\nA"])
def test_a_team_name_that_could_break_the_documents_is_refused(bad: str) -> None:
    with pytest.raises(personalize.PersonalizeError):
        personalize.check_text("The team name", bad, max_length=80)


@pytest.mark.parametrize(
    "bad",
    [
        "http://github.com/a/b",
        "https://github.com",
        "javascript:alert(1)",
        "https://a b/c",
        "github.com/a/b",
    ],
)
def test_a_repository_link_must_be_a_plain_https_address(bad: str) -> None:
    with pytest.raises(personalize.PersonalizeError):
        personalize.check_repo(bad)


def test_a_good_repository_link_loses_its_trailing_slash() -> None:
    assert personalize.check_repo("https://github.com/alpha/studyroute/") == (
        "https://github.com/alpha/studyroute"
    )


def test_the_command_refuses_a_bad_value_without_touching_any_file(
    docs: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(personalize, "ROOT", docs)
    before = {f: (docs / f).read_text(encoding="utf-8") for f in personalize.FILES}
    code = personalize.main(
        ["--team", "Bad [name]", "--repo", "https://github.com/a/b", "--no-deck"]
    )
    assert code == 2 and "Not changed" in capsys.readouterr().err
    assert {f: (docs / f).read_text(encoding="utf-8") for f in personalize.FILES} == before


def test_the_command_edits_the_documents_with_no_deck_rebuild(
    docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(personalize, "ROOT", docs)
    argv = ["--team", "Team Alpha", "--repo", "https://github.com/alpha/studyroute", "--no-deck"]
    assert personalize.main(argv) == 0
    assert "Team Alpha" in (docs / "submission/DECK_OUTLINE.md").read_text(encoding="utf-8")


def test_the_deck_builder_takes_the_values_from_the_environment() -> None:
    source = (ROOT / "submission" / "deck" / "build_deck.js").read_text(encoding="utf-8")
    assert "process.env.TEAM_NAME" in source and "process.env.REPO_LINK" in source
