import json
import shutil

import pytest

from draftvoice.store import (
    DataError,
    FIXTURES_DIR,
    list_founders,
    load_fixtures,
    load_founder,
)

SYNTHETIC = FIXTURES_DIR / "founders"


def test_only_approved_evidence_is_loaded():
    founder = load_founder("alex", SYNTHETIC)
    ids = {item.id for item in founder.evidence}
    assert ids == {"ev-001", "ev-002", "ev-003"}
    assert "ev-004" not in ids  # exists in the file, not approved


def test_unknown_founder_names_the_known_ones():
    with pytest.raises(DataError, match="alex"):
        load_founder("nobody", SYNTHETIC)


def test_evidence_from_another_founder_is_rejected(tmp_path):
    shutil.copytree(SYNTHETIC / "alex", tmp_path / "alex")
    path = tmp_path / "alex" / "evidence.json"
    items = json.loads(path.read_text())
    items[0]["founder_id"] = "rico"
    path.write_text(json.dumps(items))
    with pytest.raises(DataError, match="belongs to 'rico'"):
        load_founder("alex", tmp_path)


def test_duplicate_evidence_ids_are_rejected(tmp_path):
    shutil.copytree(SYNTHETIC / "alex", tmp_path / "alex")
    path = tmp_path / "alex" / "evidence.json"
    items = json.loads(path.read_text())
    path.write_text(json.dumps(items + [items[0]]))
    with pytest.raises(DataError, match="duplicate"):
        load_founder("alex", tmp_path)


def test_fixtures_are_synthetic_and_name_known_founders():
    fixtures = load_fixtures()
    assert len(fixtures) >= 8
    for fixture in fixtures:
        assert fixture.post.label == "synthetic"
        assert set(fixture.expected) <= set(list_founders(SYNTHETIC))


def test_real_founder_data_is_observed_and_sourced():
    for founder_id in list_founders():
        for item in load_founder(founder_id).evidence:
            assert item.label == "observed"
            assert item.source
