import pytest

from src.domain.models import ActionItem
from src.prompts.registry import PROMPTS
from src.services.evaluation_service import corpus, evaluate, match_actions, score


def test_corpus_contract():
    pairs = corpus()
    assert len(pairs) >= 20 and len({c["id"] for c, g in pairs}) == len(pairs)
    assert all(
        g["actions"] == [] or all(a["id"] and a["concepts"] for a in g["actions"]) for _, g in pairs
    )
    assert all("non fiables" in p and "suggestion" in p and "null" in p for p in PROMPTS.values())
    assert pairs[17][1]["actions"][0]["assignee"] == "Karim"


@pytest.mark.parametrize("case,gold", corpus(), ids=[c["id"] for c, _ in corpus()])
def test_annotation_matching(case, gold):
    items = [
        ActionItem.model_validate_json(
            __import__("json").dumps(
                {
                    "description": a["description"],
                    "assignee": a["assignee"],
                    "due_date": a["due_date"],
                    "priority": None,
                    "status": a["status"],
                    "source_excerpt": case["text"],
                    "requires_review": False,
                    "linked_issue_id": None,
                }
            )
        )
        for a in gold["actions"]
    ]
    assert len(match_actions(gold["actions"], items)) == len(items)


def test_paraphrase_one_to_one(reviewed):
    _, _, w = reviewed
    item = w.reports[0].extraction.actions[0]
    item.description = "Contacter le fournisseur par téléphone"
    case, gold = corpus()[0]
    assert len(match_actions(gold["actions"], [item, item])) == 1
    result = w.reports[0].extraction
    result.actions.append(item)
    row = score(case, gold, result)
    assert row.counts["fp"] == 1 and row.counts["valid_references"] == 0
    report = evaluate([(case, gold)], "hors ligne", "v2", predictions={})
    assert report.scores["echecs_parsing"] == 1 and report.scores["input_tokens"] is None


def test_released_prompt_snapshots():
    import hashlib

    expected = {
        "v1": "c08f3bc6c25740923cf3c7cca326b78c4497796cdb178989d7e385fefefac988",
        "v2": "d7244c49044bf74157d46fefc4b3f18e348a0c5cc32df2824b72a9e8f6310c19",
    }
    assert {key: hashlib.sha256(PROMPTS[key].encode()).hexdigest() for key in expected} == expected
