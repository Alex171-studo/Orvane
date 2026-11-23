import re
import unicodedata
from datetime import date, datetime, timedelta

from src.domain.errors import SchemaValidationError
from src.domain.models import (
    ActionItem,
    Clarification,
    Decision,
    ExtractionResult,
    Issue,
    Observation,
    Proposal,
)

SECTIONS = ("observations", "issues", "actions", "decisions", "clarifications")


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def prepare(value, limit):
    if len(value) > limit:
        raise SchemaValidationError("La note dépasse la limite de caractères.")
    value = normalize(value)
    if len(value) < 5:
        raise SchemaValidationError("La note doit contenir au moins cinq caractères.")
    return value


def resolve_date(expression: str | None, reference: date) -> date | None:
    if not expression:
        return None
    word = normalize(expression).lower().removeprefix("le ").replace("’", "'")
    offsets = {"aujourd'hui": 0, "demain": 1, "après-demain": 2}
    if word in offsets:
        return reference + timedelta(days=offsets[word])
    match = re.fullmatch(r"dans (\d{1,3}) jours?", word)
    if match:
        return reference + timedelta(days=int(match[1]))
    months = "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", word):
            return date.fromisoformat(word)
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", word):
            return datetime.strptime(word, "%d/%m/%Y").date()
        parts = word.split()
        if len(parts) == 3 and parts[1] in months and len(parts[2]) == 4:
            return date(int(parts[2]), months.index(parts[1]) + 1, int(parts[0]))
    except ValueError:
        pass
    return None


def integrity(result: ExtractionResult, source: str, enforce_sources=True):
    ids = set()
    source = normalize(source)
    for section in SECTIONS:
        seen = set()
        for item in getattr(result, section):
            signature = item.model_dump_json(exclude={"id", "requires_review", "source_excerpt"})
            if item.id in ids or signature in seen:
                raise SchemaValidationError(
                    "Identifiant ou élément en double. Fusionnez les propositions."
                )
            seen.add(signature)
            ids.add(item.id)
            if enforce_sources and normalize(item.source_excerpt) not in source:
                raise SchemaValidationError(
                    "Une citation est absente de la note. Corrigez-la avant validation."
                )
    issue_ids = {item.id for item in result.issues}
    if any(a.linked_issue_id and a.linked_issue_id not in issue_ids for a in result.actions):
        raise SchemaValidationError("Une action référence un problème absent.")
    if any(c.related_entity_id and c.related_entity_id not in ids for c in result.clarifications):
        raise SchemaValidationError("Une clarification référence un élément absent.")


def referenced(items, index):
    if index is None:
        return None
    if index >= len(items):
        raise SchemaValidationError("Relation proposée hors limites.")
    return items[index].id


def materialize(raw: Proposal, source: str, reference: date) -> ExtractionResult:
    def convert(model, items):
        return [model(**i.model_dump()) for i in items]

    issues = convert(Issue, raw.issues)
    actions = []
    questions = []
    for item in raw.actions:
        expression = item.due_expression
        due = (
            resolve_date(expression, reference)
            if expression
            and re.search(
                r"(?<![\w/-])" + re.escape(expression) + r"(?![\w/-])", item.source_excerpt, re.I
            )
            else None
        )
        action = ActionItem(
            **item.model_dump(exclude={"issue_index", "due_expression"}),
            linked_issue_id=referenced(issues, item.issue_index),
            due_date=due,
        )
        reasons = []
        if action.assignee and not re.search(
            r"(?<!\w)" + re.escape(action.assignee) + r"(?!\w)", item.source_excerpt, re.I
        ):
            reasons.append("Le responsable proposé ne figure pas dans la citation.")
            action.assignee = None
        if expression and due is None:
            reasons.append("L'échéance proposée est ambiguë ou non étayée.")
        if not action.assignee or not due or not action.priority or reasons:
            action.requires_review = True
        if reasons:
            questions.append(
                Clarification(
                    question="Quelles précisions apporter à cette action ?",
                    reason=" ".join(reasons),
                    source_excerpt=item.source_excerpt,
                    related_entity_id=action.id,
                )
            )
        actions.append(action)
    for item in raw.clarifications:
        questions.append(
            Clarification(
                **item.model_dump(exclude={"action_index"}),
                related_entity_id=referenced(actions, item.action_index),
            )
        )
    result = ExtractionResult(
        summary=raw.summary,
        observations=convert(Observation, raw.observations),
        issues=issues,
        actions=actions,
        decisions=convert(Decision, raw.decisions),
        clarifications=questions,
    )
    for issue in issues:
        issue.requires_review |= issue.severity is None or issue.operational_impact is None
    for section in SECTIONS[:-1]:
        for item in getattr(result, section):
            if normalize(item.source_excerpt) not in normalize(source):
                item.requires_review = True
    integrity(result, source, enforce_sources=False)
    return result


def detach_removed(previous: ExtractionResult, updated: ExtractionResult) -> None:
    """Détacher uniquement les relations dont la cible vient d’être supprimée en revue."""
    removed = {item.id for section in SECTIONS for item in getattr(previous, section)} - {
        item.id for section in SECTIONS for item in getattr(updated, section)
    }
    for action in updated.actions:
        if action.linked_issue_id in removed:
            action.linked_issue_id = None
    for question in updated.clarifications:
        if question.related_entity_id in removed:
            question.related_entity_id = None
