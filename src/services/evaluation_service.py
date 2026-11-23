import json
import re
import unicodedata
from collections import Counter
from datetime import datetime
from statistics import mean

from pydantic import Field

from src.domain.errors import OrvaneError, SchemaValidationError
from src.domain.models import ExtractionResult, Model, ProjectContext
from src.providers.demo_provider import DATA, DemoProvider, examples
from src.services.extraction_service import FieldIntelligencePipeline
from src.services.validation_service import SECTIONS, normalize


class CaseScore(Model):
    id: str
    matches: dict[str, str]
    counts: dict[str, int]
    duration_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None


class EvaluationReport(Model):
    model: str
    prompt_version: str
    source: str
    scores: dict[str, float | int | None]
    cases: list[CaseScore] = Field(min_length=1)


def corpus():
    cases = json.loads((DATA / "evaluation/cases.json").read_text())
    gold = json.loads((DATA / "evaluation/expected_outputs.json").read_text())
    by_id = {g["id"]: g for g in gold}
    if len(cases) != len(gold) or len(by_id) != len(gold) or {c["id"] for c in cases} != set(by_id):
        raise ValueError("Identifiants du corpus incohérents.")
    return [(case, by_id[case["id"]]) for case in cases]


def words(value):
    plain = unicodedata.normalize("NFKD", value.casefold())
    return set(re.findall(r"[a-z0-9]+", "".join(c for c in plain if not unicodedata.combining(c))))


def match_actions(gold, predicted):
    candidates = []
    for ref in gold:
        choices = []
        for i, item in enumerate(predicted):
            tokens = words(item.description)
            if all(any(words(alias) <= tokens for alias in group) for group in ref["concepts"]):
                choices.append(i)
        candidates.append(choices)
    # Augmenting paths give maximum cardinality; input order breaks ties reproducibly.
    owners = {}

    def assign(index, visited):
        for item in candidates[index]:
            if item in visited:
                continue
            visited.add(item)
            if item not in owners or assign(owners[item], visited):
                owners[item] = index
                return True
        return False

    for index in range(len(gold)):
        assign(index, set())
    return {ref: item for item, ref in owners.items()}


def score(case, gold, result, error=None, metrics=()):
    predicted = result.actions if result else []
    expected = gold["actions"]
    pairs = match_actions(expected, predicted)
    counts = Counter(
        tp=len(pairs),
        fp=len(predicted) - len(pairs),
        fn=len(expected) - len(pairs),
        parse_errors=int(error == "SchemaValidationError"),
        failures=int(error is not None),
    )
    for i, j in pairs.items():
        ref, item = expected[i], predicted[j]
        counts["assignees"] += words(ref["assignee"] or "") == words(item.assignee or "")
        counts["dates"] += ref["due_date"] == (item.due_date.isoformat() if item.due_date else None)
        counts["statuses"] += ref["status"] == item.status.value
    for goal in gold["observations"]:
        counts["work_expected"] += 1
        counts["work_correct"] += bool(
            result
            and any(
                words(goal["concept"]) <= words(o.description)
                and o.work_status.value == goal["status"]
                for o in result.observations
            )
        )
    if result:
        for section in SECTIONS:
            for item in getattr(result, section):
                counts["references"] += 1
                counts["valid_references"] += normalize(item.source_excerpt) in normalize(
                    case["text"]
                )
        counts["decision_count_correct"] = int(len(result.decisions) == gold["decisions"])
        counts["issue_count_correct"] = int(len(result.issues) == gold["issues"])
        if gold["clarification"]:
            counts["clarified"] = int(
                bool(result.clarifications)
                or any(x.requires_review for s in SECTIONS[:-1] for x in getattr(result, s))
            )
    counts["ambiguous"] = int(gold["clarification"])

    def total(field):
        values = [getattr(m, field) for m in metrics]
        return (
            sum(v for v in values if v is not None) if any(v is not None for v in values) else None
        )

    return CaseScore(
        id=case["id"],
        matches={expected[i]["id"]: str(predicted[j].id) for i, j in pairs.items()},
        counts=dict(counts),
        duration_ms=total("duration_ms"),
        input_tokens=total("input_tokens"),
        output_tokens=total("output_tokens"),
        error=error,
    )


def aggregate(rows, model, version, source):
    c = Counter()
    for row in rows:
        c.update(row.counts)

    def ratio(a, b):
        return a / b if b else None

    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    scores = {
        "precision_actions": ratio(tp, tp + fp),
        "rappel_actions": ratio(tp, tp + fn),
        "f1_actions": ratio(2 * tp, 2 * tp + fp + fn),
        "fausses_actions": ratio(fp, tp + fp),
        "responsables_exacts": ratio(c["assignees"], tp),
        "dates_exactes": ratio(c["dates"], tp),
        "statuts_actions_exacts": ratio(c["statuses"], tp),
        "avancements_exacts": ratio(c["work_correct"], c["work_expected"]),
        "references_valides": ratio(c["valid_references"], c["references"]),
        "echecs_parsing": c["parse_errors"] / len(rows),
        "echecs_traitement": c["failures"] / len(rows),
        "decisions_nombre_exact": c["decision_count_correct"] / len(rows),
        "problemes_nombre_exact": c["issue_count_correct"] / len(rows),
        "ambiguites_signalees": ratio(c["clarified"], c["ambiguous"]),
    }
    for field in ("duration_ms", "input_tokens", "output_tokens"):
        values = [getattr(row, field) for row in rows if getattr(row, field) is not None]
        scores["latence_moyenne_ms" if field == "duration_ms" else field] = (
            (mean(values) if field == "duration_ms" else sum(values)) if values else None
        )
    return EvaluationReport(
        model=model, prompt_version=version, source=source, scores=scores, cases=rows
    )


def evaluate(pairs, model, version, pipeline=None, runtime=None, predictions=None):
    rows = []
    for case, gold in pairs:
        result = None
        error = None
        start = len(runtime.metrics) if runtime else 0
        try:
            if pipeline:
                context = ProjectContext(
                    name=case["project"],
                    location=case["location"],
                    reference_timezone="Europe/Paris",
                )
                result = pipeline.analyze(
                    case["text"], context, datetime.fromisoformat(case["reference_datetime"])
                )
            elif predictions is not None and case["id"] in predictions:
                result = ExtractionResult.model_validate_json(json.dumps(predictions[case["id"]]))
            else:
                raise SchemaValidationError("Prédiction manquante.")
        except OrvaneError as exc:
            error = type(exc).__name__
        except ValueError:
            error = "SchemaValidationError"
        rows.append(score(case, gold, result, error, runtime.metrics[start:] if runtime else []))
    return aggregate(
        rows,
        model,
        version,
        "api" if pipeline else "fichier",
    )


def replay_demo(settings):
    targets = json.loads((DATA / "evaluation/demo_targets.json").read_text())
    pairs = []
    for sample, target in zip(examples(), targets, strict=True):
        case = {
            "id": target["id"],
            "project": sample.name,
            "location": sample.location,
            "text": sample.text,
            "reference_datetime": sample.reference_datetime,
        }
        pairs.append((case, target))
    return evaluate(
        pairs,
        "Fixtures de démonstration",
        "sans prompt",
        pipeline=FieldIntelligencePipeline(DemoProvider(), settings),
    ).model_copy(update={"source": "fixtures"})
