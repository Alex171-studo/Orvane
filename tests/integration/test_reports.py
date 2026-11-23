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
