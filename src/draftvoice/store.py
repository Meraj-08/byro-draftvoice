"""Load founder data and fixtures from JSON files. Only approved evidence leaves this module."""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from draftvoice.models import Evidence, Fixture, VoiceProfile

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "founders"
FIXTURES_DIR = ROOT / "fixtures"


class DataError(ValueError):
    pass


@dataclass(frozen=True)
class Founder:
    profile: VoiceProfile
    evidence: tuple[Evidence, ...]  # approved only

    @property
    def id(self) -> str:
        return self.profile.founder_id


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise DataError(f"missing file: {path}") from exc


def load_founder(founder_id: str, founders_dir: Path = DATA_DIR) -> Founder:
    folder = founders_dir / founder_id
    if not folder.is_dir():
        known = ", ".join(list_founders(founders_dir)) or "none"
        raise DataError(f"unknown founder '{founder_id}' (known: {known})")

    profile = VoiceProfile.model_validate(_read_json(folder / "profile.json"))
    evidence = TypeAdapter(list[Evidence]).validate_python(
        _read_json(folder / "evidence.json")
    )

    if profile.founder_id != founder_id:
        raise DataError(f"{folder}/profile.json belongs to '{profile.founder_id}'")
    seen: set[str] = set()
    for item in evidence:
        if item.founder_id != founder_id:
            raise DataError(f"evidence {item.id} belongs to '{item.founder_id}'")
        if item.id in seen:
            raise DataError(f"duplicate evidence id {item.id}")
        seen.add(item.id)

    return Founder(profile, tuple(item for item in evidence if item.approved))


def find_founder(founder_id: str) -> Founder:
    """Real founders first, then the synthetic test founders."""
    if founder_id in list_founders(DATA_DIR):
        return load_founder(founder_id, DATA_DIR)
    if founder_id in list_founders(FIXTURES_DIR / "founders"):
        return load_founder(founder_id, FIXTURES_DIR / "founders")
    known = ", ".join(list_founders(DATA_DIR) + list_founders(FIXTURES_DIR / "founders"))
    raise DataError(f"unknown founder '{founder_id}' (known: {known})")


def list_founders(founders_dir: Path = DATA_DIR) -> list[str]:
    if not founders_dir.is_dir():
        return []
    return sorted(p.name for p in founders_dir.iterdir() if (p / "profile.json").exists())


def load_fixtures(path: Path = FIXTURES_DIR / "posts.json") -> list[Fixture]:
    fixtures = TypeAdapter(list[Fixture]).validate_python(_read_json(path))
    ids = [f.post.id for f in fixtures]
    if len(ids) != len(set(ids)):
        raise DataError("duplicate post id in fixtures")
    return fixtures
