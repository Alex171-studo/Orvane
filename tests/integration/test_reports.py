from datetime import UTC, datetime
from io import BytesIO

from pypdf import PdfReader

from src.domain.models import Status
from src.services.analytics_service import corrections, indicators
from src.services.reporting_service import render_pdf


def test_dashboard_and_revision(reviewed):
    repo, wf, w = reviewed
    assert indicators(repo)["reports"] == 0
    wf.validate(w)
    instant = datetime(2026, 11, 27, tzinfo=UTC)
    assert indicators(repo, instant) == dict(
        reports=1, issues=1, open_actions=1, overdue=1, mean_ms=None
    )
    changed = w.reports[0].extraction.model_copy(deep=True)
    changed.actions[0].status = Status.DONE
    changed.issues[0].is_open = False
    wf.edit(w, changed)
    assert indicators(repo, instant)["overdue"] == 1
    wf.validate(w)
    assert indicators(repo)["open_actions"] == 0 and indicators(repo)["issues"] == 0
    assert corrections(repo) == (2, 2 / 5)


def test_multipage_pdf(reviewed):
    repo, wf, w = reviewed
    r = w.reports[0]
    project = repo.project(r.project_id)
    draft = render_pdf(r, project)
    assert "BROUILLON" in PdfReader(BytesIO(draft)).pages[0].extract_text()
    wf.validate(w)
    report = r.model_copy(deep=True)
    report.extraction.actions[0].description = "<b>Échéance & matériel</b> " * 500
    pdf = render_pdf(report, project)
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) > 1 and pdf == render_pdf(report, project)
    content = " ".join(p.extract_text() for p in reader.pages)
    assert "VALIDÉ" in content and "Échéance &" in content and "Page 2" in content


def test_field_note_separates_completed_work_from_actions(session):
    from src.domain.models import Proposal, WorkStatus
    from src.services.validation_service import materialize

    supplier = "Le fournisseur n’a toujours pas livré les fenêtres."
    call = "Karim doit le rappeler vendredi."
    done = "Le contrôle électrique est terminé"
    leak = "une infiltration a été découverte au troisième étage."
    notify = "Il faut prévenir le responsable technique."
    note = f"{supplier} {call} {done}, mais {leak} {notify}"
    raw = {
        "summary": f"{supplier} {done}.",
        "observations": [
            dict(
                description=done,
                category="Avancement",
                work_status="Terminé",
                source_excerpt=done,
                requires_review=False,
            )
        ],
        "issues": [
            dict(
                title=issue,
                description=issue,
                severity=None,
                operational_impact=None,
                source_excerpt=issue,
                requires_review=True,
            )
            for issue in (supplier, leak)
        ],
        "actions": [
            dict(
                description="Relancer le fournisseur",
                assignee="Karim",
                due_expression="vendredi",
                priority=None,
                status="À faire",
                issue_index=0,
                source_excerpt=call,
                requires_review=False,
            ),
            dict(
                description="Prévenir le responsable technique",
                assignee=None,
                due_expression=None,
                priority=None,
                status="À faire",
                issue_index=None,
                source_excerpt=notify,
                requires_review=True,
            ),
        ],
        "decisions": [],
        "clarifications": [],
    }
    import json

    repo, wf, work, _, pipeline = session
    proposal = Proposal.model_validate_json(json.dumps(raw))
    result = materialize(proposal, note, work.reference_datetime.date())
    assert len(result.actions) == 2 and result.observations[0].work_status == WorkStatus.DONE
    assert result.actions[0].due_date.isoformat() == "2026-11-27"
    assert result.actions[1].requires_review and result.actions[1].assignee is None
    pipeline.provider.extract.return_value = proposal
    wf.transcribe(work, note)
    wf.approve(work)
    report = wf.analyze(work, pipeline)
    wf.validate(work)
    pdf = PdfReader(BytesIO(render_pdf(report, repo.project(report.project_id))))
    content = " ".join(page.extract_text() for page in pdf.pages)
    assert "Extraits de la note" in content and "27/11/2026" in content and call in content
