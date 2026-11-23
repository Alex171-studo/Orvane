from statistics import mean
from zoneinfo import ZoneInfo

from src.domain.models import ExtractionResult, Status, now
from src.services.validation_service import SECTIONS


def current_reports(repo):
    for work in repo.data.works:
        latest = next((r for r in reversed(work.reports) if r.status == "validated"), None)
        if latest:
            yield work, latest


def indicators(repo, instant=None):
    reports = list(current_reports(repo))
    actions = [
        (
            a,
            (instant or now())
            .astimezone(ZoneInfo(repo.project(r.project_id).reference_timezone))
            .date(),
        )
        for _, r in reports
        for a in r.extraction.actions
        if a.status != Status.DONE
    ]
    timings = [m.duration_ms for m in repo.data.metrics if m.error_type is None]
    return {
        "reports": len(reports),
        "issues": sum(i.is_open for _, r in reports for i in r.extraction.issues),
        "open_actions": len(actions),
        "overdue": sum(bool(a.due_date and a.due_date < today) for a, today in actions),
        "mean_ms": mean(timings) if timings else None,
    }


def corrections(repo):
    proposed = set()
    changed = set()
    edits = 0
    for event in repo.data.audit:
        if event.event_type == "proposed" and event.after:
            extraction = ExtractionResult.model_validate_json(event.after)
            proposed.add(event.entity_id)
            proposed.update(item.id for sec in SECTIONS for item in getattr(extraction, sec))
        if event.event_type in ("entity_edit", "summary_edit"):
            edits += 1
            changed.add(event.entity_id)
    # Summary changes in later revisions refer to the original proposal of the same note.
    for w in repo.data.works:
        original = None
        for r in w.reports:
            if r.id in proposed:
                original = r.id
            if r.id in changed and original:
                changed.add(original)
    return edits, len(proposed & changed) / len(proposed) if proposed else None
