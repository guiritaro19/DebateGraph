import json

from app.config.settings import ROOT


def candidates():
    return json.loads((ROOT / "data/candidates/candidates.json").read_text(encoding="utf-8"))


def candidate(candidate_id):
    for item in candidates():
        if item["id"] == candidate_id:
            return item
    raise ValueError(f"Unknown candidate: {candidate_id}")


def topics():
    return json.loads((ROOT / "data/topics.json").read_text(encoding="utf-8"))
