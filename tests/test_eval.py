import json

from draftvoice import eval as evaluation
from draftvoice import validate as checks
from draftvoice.cli import main
from draftvoice.model import ModelError
from draftvoice.store import FIXTURES_DIR

REPORT = evaluation.run()


def test_design_checks_all_pass():
    assert REPORT.design and REPORT.ok


def test_wilson_interval():
    lo, hi = evaluation.wilson(14, 20)
    assert round(lo, 2) == 0.48 and round(hi, 2) == 0.85
    assert evaluation.wilson(0, 0) == (0.0, 0.0)
    assert evaluation.wilson(0, 44)[0] < 1e-9


def test_every_unseen_lie_is_measured():
    items = json.loads((FIXTURES_DIR / "unseen_lies.json").read_text())["items"]
    assert len(REPORT.unseen) == len(items) >= 15
    assert all(u[3] in ("blocked", "slipped") for u in REPORT.unseen)
    assert all(u[6] for u in REPORT.unseen if u[3] == "slipped")  # every slip has a reason


def test_real_contributions_are_parsed_from_evidence():
    contribs = evaluation.contributions()
    assert {c.founder_id for c in contribs} == {"rico", "fathin"}
    assert not any(c.text.startswith("(") or "[person]" in c.text for c in contribs)
    assert {"RS-20", "FD-07"} <= {c.id for c in contribs if c.is_contribution}


def test_leave_one_out_removes_the_item_under_test():
    from draftvoice.store import load_founder
    rico = load_founder("rico")
    held_out = evaluation._without(rico, "RS-01", "i just use Byro")
    assert "RS-01" not in {e.id for e in held_out.evidence}
    assert "i just use Byro" not in held_out.profile.examples


def test_behaviour_labels_follow_the_derivation_rule():
    for _, _, expected, *_ in REPORT.behaviour:
        assert expected in ("draft", "do nothing")
    assert len(REPORT.behaviour) == sum(c.on_others_post for c in evaluation.contributions())


def test_threshold_sweep_leaves_the_code_threshold_unchanged():
    assert [row[0] for row in REPORT.v6] == list(evaluation.THRESHOLDS)
    assert checks.REPEAT_SIMILARITY == 0.8


def test_report_layout():
    text = evaluation.render(REPORT)
    main, collapsed = text.split("<details>")
    assert "Directional, not statistical." in main
    assert "95% range" in main and "## Known gaps" in main and "## What this does not show" in main
    assert "## Design checks" in main and "relative_claim" not in main
    assert "social" not in text and "substantive" not in text and "eval-details" not in text
    assert len(main.splitlines()) <= 80
    assert text.count("<details>") == 1 and "The lie" in collapsed
    assert all(u[0] in collapsed for u in REPORT.unseen)


def test_model_errors_are_reported_not_passed():
    class Down:
        name = "down"

        def draft(self, request):
            raise ModelError("503")

    report = evaluation.run(live=Down())
    assert report.live and all(row[2] == "model error" for row in report.live)


def test_cli_writes_the_report(tmp_path, capsys):
    out = tmp_path / "report.md"
    assert main(["eval", "--out", str(out)]) == 0
    assert not (tmp_path / "eval-details.md").exists()
    assert "Lies the checks had never seen (synthetic, written by Gemini)" in capsys.readouterr().out
