"""The six official deliverables exist and say what they must (competition rules, Appendix 2)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DELIVERABLES = {
    "01 technical documentation": "docs/TECHNICAL_DOCUMENTATION.md",
    "02 presentation deck (slide text)": "submission/DECK_OUTLINE.md",
    "02 presentation deck (file)": "submission/StudyRoute_Deck.pptx",
    "03 demo video script": "submission/VIDEO_SCRIPT.md",
    "04 README": "README.md",
    "04 test cases": "docs/TEST_CASES.md",
    "04 third-party licences": "docs/THIRD_PARTY.md",
    "05 security self-assessment": "docs/SECURITY_SELF_ASSESSMENT.md",
    "06 evidence: operation log": "submission/evidence/sandbox_operation_log.txt",
    "06 evidence: audit log": "submission/evidence/audit_log.json",
    "06 evidence: verify result": "submission/evidence/audit_verify.json",
    "06 evidence: tamper demo": "submission/evidence/tamper_demo.json",
}


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize(("name", "path"), DELIVERABLES.items())
def test_each_deliverable_exists_and_is_not_empty(name: str, path: str) -> None:
    assert (ROOT / path).is_file(), name
    assert len((ROOT / path).read_bytes().strip()) > 100, name


def test_the_technical_documentation_covers_the_three_things_the_rules_ask_for() -> None:
    text = read("docs/TECHNICAL_DOCUMENTATION.md")
    for heading in ("## 1. System architecture", "## 2. Core algorithms", "## 3. Security design"):
        assert heading in text


def test_every_blueprint_scenario_is_mapped_to_a_test_in_the_test_case_document() -> None:
    text = read("docs/TEST_CASES.md")
    rows = re.findall(r"^\| (T\d\d) \|", text, re.M)
    assert rows == [f"T{n:02d}" for n in range(1, 25)]
    assert "MISSING" not in text


def test_the_licence_inventory_has_no_unknown_licences() -> None:
    assert "see package" not in read("docs/THIRD_PARTY.md")


def test_the_execution_evidence_shows_a_passing_chain_and_a_detected_tamper() -> None:
    verify = json.loads(read("submission/evidence/audit_verify.json"))
    assert verify["status"] == "PASS" and verify["events_checked"] > 10
    tamper = json.loads(read("submission/evidence/tamper_demo.json"))
    assert tamper["verify_after_edit"]["status"] == "FAIL"
    assert tamper["verify_after_edit"]["failed_seq"] == tamper["edited_event"]["seq"]
    assert tamper["verify_after_restore"]["status"] == "PASS"
    log = read("submission/evidence/sandbox_operation_log.txt")
    assert not [line for line in log.splitlines() if line.strip().startswith("FAIL")]
    assert "payment reaches SETTLED" in log
    for step in (
        "Agent tasks",
        "Compliance report",
        "all 10 controls pass",
        "no payment was created by the assistant",
    ):
        assert step in log, step


def test_the_checklist_states_the_team_size_rule_and_the_deadline() -> None:
    text = read("submission/CHECKLIST.md")
    assert "2 to 5 students" in text
    assert "20 Oct 2026, 23:59 Beijing" in text
    for number in ("01", "02", "03", "04", "05", "06"):
        assert f"| {number} |" in text


def test_the_deck_is_a_real_twenty_slide_powerpoint_file_with_speaker_notes() -> None:
    import zipfile

    with zipfile.ZipFile(ROOT / "submission" / "StudyRoute_Deck.pptx") as deck:
        names = deck.namelist()
        slides = [n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        notes = [n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)]
        assert len(slides) == 20, "about half a minute each, inside the 10-minute cap"
        assert len(notes) == 20
        words = sum(
            len(" ".join(re.findall(r"<a:t>([^<]*)</a:t>", deck.read(n).decode("utf-8"))).split())
            - 1
            for n in notes
        )
        assert words / 150 <= 10, (
            "the speaker notes must fit the 10-minute cap at 150 words a minute"
        )
        theme = deck.read("ppt/theme/theme1.xml").decode("utf-8")
        assert 'name="StudyRoute"' in theme and "0B2545" in theme
