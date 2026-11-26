import json

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from src.domain.errors import SchemaValidationError
from src.domain.models import (
    ActionItem,
    Clarification,
    Decision,
    ExtractionResult,
    Issue,
    Observation,
    Priority,
    Severity,
    Status,
    WorkStatus,
)
from src.services.validation_service import SECTIONS, detach_removed, normalize

MODELS = dict(zip(SECTIONS, (Observation, Issue, ActionItem, Decision, Clarification), strict=True))
LABELS = {
    "observations": "Avancement et observations",
    "issues": "Problèmes",
    "actions": "Plan d’action",
    "decisions": "Décisions",
    "clarifications": "Points à clarifier",
}
NAMES = {
    "description": "Description",
    "source_excerpt": "Citation source",
    "requires_review": "À vérifier",
    "work_status": "Avancement",
    "title": "Intitulé",
    "category": "Catégorie",
    "severity": "Sévérité",
    "operational_impact": "Impact",
    "is_open": "Ouvert",
    "assignee": "Responsable",
    "due_date": "Échéance",
    "priority": "Priorité",
    "status": "Statut",
    "question": "Question",
    "reason": "Motif",
    "review": "Origine",
}
OPTIONS = {
    "priority": list(Priority),
    "severity": list(Severity),
    "status": list(Status),
    "work_status": list(WorkStatus),
    "category": ["Avancement", "Observation", "Risque"],
}
HIDDEN = ("id", "linked_issue_id", "related_entity_id")


def editor(section, items, key, changed, validated=False, projects=None):
    model = MODELS[section]
    rows = []
    for item in items:
        row = item.model_dump(mode="json")
        row["review"] = (
            "Validé" if validated else "Modifié" if item.id in changed else "Proposé par l’IA"
        )
        if projects:
            row["project"] = projects[item.id]
        if isinstance(item, ActionItem):
            row["due_date"] = item.due_date
        rows.append(row)
    columns = list(model.model_fields) + ["review"] + (["project"] if projects else [])
    frame = pd.DataFrame(rows, columns=columns)
    config = {}
    for col in columns:
        if col in HIDDEN:
            config[col] = None
        elif col in OPTIONS:
            config[col] = st.column_config.SelectboxColumn(
                NAMES[col], options=[str(x) for x in OPTIONS[col]]
            )
        elif col == "due_date":
            config[col] = st.column_config.DateColumn("Échéance", format="DD/MM/YYYY")
        elif col in ("requires_review", "is_open"):
            config[col] = st.column_config.CheckboxColumn(NAMES[col], default=True)
        else:
            config[col] = st.column_config.TextColumn(NAMES.get(col, "Chantier"))
    order = [
        c
        for c in (
            "description",
            "question",
            "title",
            "assignee",
            "project",
            "priority",
            "due_date",
            "status",
            "source_excerpt",
        )
        if c in columns
    ]
    order += [c for c in columns if c not in order and c not in HIDDEN]
    edited = st.data_editor(
        frame,
        key=key,
        hide_index=True,
        column_config=config,
        column_order=order,
        disabled=["review", "project", *HIDDEN],
        num_rows="fixed" if projects else "dynamic",
        width="stretch",
    )
    return edited


def parse_rows(section, frame):
    model = MODELS[section]
    result = []
    for row in frame.to_dict("records"):
        clean = {
            k: (None if pd.isna(v) or v == "" else v)
            for k, v in row.items()
            if k in model.model_fields
        }
        if not clean.get("id"):
            clean.pop("id", None)
        try:
            result.append(model.model_validate_json(json.dumps(clean, default=str)))
        except ValidationError as exc:
            field = exc.errors(include_input=False)[0]["loc"][0]
            raise SchemaValidationError(
                f"{LABELS[section]} : vérifiez le champ « {NAMES.get(field, field)} »."
            ) from None
    return result


def review(repo, wf, w):
    report = w.reports[-1]
    result = report.extraction
    changed = {
        e.entity_id for e in repo.data.audit if e.event_type in ("entity_edit", "summary_edit")
    }
    st.subheader(
        f"Version {report.revision} · "
        + ("Validée" if report.status == "validated" else "À valider")
    )
    if report.id in changed:
        st.caption("MODIFIÉ · Synthèse corrigée")
    source = normalize(report.source_text)
    missing = [
        f"{LABELS[name]} · ligne {n}"
        for name in SECTIONS
        for n, item in enumerate(getattr(result, name), 1)
        if normalize(item.source_excerpt) not in source
    ]
    if missing:
        st.error("Citations à corriger avant validation : " + ", ".join(missing))
    cols = st.columns(3)
    flagged = {
        i.id
        for sec in SECTIONS
        for i in getattr(result, sec)
        if getattr(i, "requires_review", False)
    }
    extra = sum(c.related_entity_id not in flagged for c in result.clarifications)
    cols[0].metric("Actions", len(result.actions))
    cols[1].metric("Points à vérifier", len(flagged) + extra)
    cols[2].metric("Actions terminées", sum(a.status == Status.DONE for a in result.actions))
    order = ("actions", "observations", "issues", "decisions", "clarifications")
    key = f"review-{report.id}-{len(repo.data.audit)}"
    with st.form(key):
        summary = st.text_area("Synthèse opérationnelle", result.summary)
        tabs = st.tabs([LABELS[s] + f" ({len(getattr(result, s))})" for s in order])
        frames = {}
        for section, tab in zip(order, tabs, strict=True):
            with tab:
                frames[section] = editor(
                    section,
                    getattr(result, section),
                    key + section,
                    changed,
                    report.status == "validated",
                )
        save = st.form_submit_button("Enregistrer les modifications")
        validate = st.form_submit_button(
            "Valider le compte rendu", type="primary", disabled=report.status == "validated"
        )
    if save or validate:
        candidate = ExtractionResult(
            summary=summary, **{s: parse_rows(s, f) for s, f in frames.items()}
        )
        detach_removed(result, candidate)
        if validate:
            from src.services.validation_service import integrity

            integrity(candidate, w.note.text)
        wf.edit(w, candidate)
        if validate:
            wf.validate(w)
        st.rerun()


def read_report(result):
    st.subheader("Synthèse validée")
    st.text(result.summary)
    st.subheader("Plan d’action")
    if result.actions:
        st.dataframe(
            [
                {
                    "Action": a.description,
                    "Responsable": a.assignee or "À désigner",
                    "Échéance": a.due_date.strftime("%d/%m/%Y") if a.due_date else "À définir",
                    "Priorité": a.priority or "À confirmer",
                    "Statut": a.status,
                }
                for a in result.actions
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("Aucune action consignée.")
    for section in ("observations", "issues", "decisions", "clarifications"):
        items = getattr(result, section)
        if items:
            st.subheader(LABELS[section])
            for item in items:
                if section == "clarifications":
                    st.text(f"{item.question} {item.reason}")
                elif section == "observations":
                    st.text(f"{item.work_status} · {item.description}")
                else:
                    st.text(item.description)
    with st.expander("Sources et points à vérifier"):
        for section in SECTIONS:
            for item in getattr(result, section):
                flagged = getattr(item, "requires_review", section == "clarifications")
                label = getattr(item, "description", None) or item.question
                st.text(f"{label}" + (" · À vérifier" if flagged else ""))
                st.text(f"« {item.source_excerpt} »")
