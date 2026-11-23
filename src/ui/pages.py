from datetime import date as calendar_date
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from src.domain.models import Project, Stage, now
from src.providers.demo_provider import DemoProvider, examples
from src.providers.groq_transcription import GroqTranscriptionService
from src.providers.openai_extraction import OpenAIExtractionService
from src.services.analytics_service import corrections, current_reports, indicators
from src.services.audio_service import MIMES
from src.services.extraction_service import FieldIntelligencePipeline
from src.services.reporting_service import render_pdf
from src.ui.editors import editor, parse_rows, review
from src.ui.styles import metric_grid

NAV = ["Vue d’ensemble", "Nouveau compte rendu", "Plan d’action", "Rapports", "Qualité IA"]


def navigate(index):
    st.session_state.nav = NAV[index]


def overview(repo):
    st.title(NAV[0])
    values = indicators(repo)
    mean = values["mean_ms"]
    metric_grid(
        [
            ("Rapports validés", values["reports"]),
            ("Problèmes ouverts", values["issues"]),
            ("Actions ouvertes", values["open_actions"]),
            ("Actions en retard", values["overdue"]),
            ("Traitement moyen", "—" if mean is None else f"{mean / 1000:.1f} s"),
        ]
    )
    st.button("Créer un compte rendu", type="primary", on_click=navigate, args=(1,))
    reports = list(current_reports(repo))
    if reports:
        rows = [
            {"Chantier": repo.project(r.project_id).name, "Statut": a.status.value}
            for _, r in reports
            for a in r.extraction.actions
        ]
        if rows:
            chart = px.bar(
                pd.DataFrame(rows).value_counts().rename("Actions").reset_index(),
                x="Chantier",
                y="Actions",
                color="Statut",
                color_discrete_sequence=["#172554", "#2563EB", "#15803D"],
            )
            chart.update_layout(
                height=310, margin=dict(t=12, b=12, l=12, r=12), legend_title_text=""
            )
            st.subheader("Répartition des actions")
            st.plotly_chart(chart, width="stretch")
    st.subheader("Chantiers suivis")
    if not repo.data.projects:
        st.info("Créez votre premier chantier dans « Nouveau compte rendu ».")
    else:
        st.dataframe(
            [
                {
                    "Chantier": p.name,
                    "Localisation": p.location,
                    "Rapports validés": sum(r.project_id == p.id for _, r in reports),
                }
                for p in repo.data.projects
            ],
            hide_index=True,
            width="stretch",
        )


def acquisition(repo, wf, cfg, runtime):
    st.title(NAV[1])
    if repo.data.works:
        options = [None] + [w.note.id for w in reversed(repo.data.works)]
        wid = st.selectbox(
            "Dossier de travail",
            options,
            key="working_note",
            format_func=lambda i: "Nouvelle note" if i is None else note_label(repo, repo.work(i)),
        )
    else:
        wid = None
    if wid is None:
        st.subheader("1 · Chantier")
        if cfg.APP_MODE == "live":
            with st.expander("Ajouter un chantier", expanded=not repo.data.projects):
                with st.form("add-project"):
                    name = st.text_input("Nom du chantier")
                    place = st.text_input("Localisation")
                    if st.form_submit_button("Créer le chantier"):
                        project = Project(
                            name=name, location=place, reference_timezone=cfg.APP_TIMEZONE
                        )
                        repo.data.projects.append(project)
                        repo.event(project.id, "project", None, project.model_dump_json())
                        st.rerun()
        if not repo.data.projects:
            return
        project = st.selectbox("Chantier", repo.data.projects, format_func=lambda p: p.name)
        demo = (
            next((ex for ex in examples() if ex.name == project.name), None)
            if cfg.APP_MODE == "demo"
            else None
        )
        tz = ZoneInfo(project.reference_timezone)
        date = st.date_input(
            "Date de référence",
            datetime.fromisoformat(demo.reference_datetime).date()
            if demo
            else now().astimezone(tz).date(),
        )
        source = st.radio(
            "2 · Source",
            ["Note préenregistrée"]
            if cfg.APP_MODE == "demo"
            else ["Texte", "Microphone", "Fichier audio"],
            horizontal=True,
        )
        if st.button("Ouvrir la note", type="primary"):
            w = wf.create(
                project,
                datetime.combine(date, time(12), tzinfo=tz),
                "demo" if demo else "text" if source == "Texte" else "audio",
            )
            if demo:
                wf.transcribe(w, demo.text)
            st.session_state[f"method-{w.note.id}"] = source
            st.session_state.next_note = w.note.id
            st.rerun()
        return
    w = repo.work(wid)
    st.text(note_label(repo, w))
    if w.note.source_type == "audio" and w.stage == Stage.NEW:
        st.subheader("2 · Note audio")
        choice = st.radio(
            "Entrée audio",
            ["Microphone", "Fichier audio"],
            index=int(st.session_state.get(f"method-{wid}") == "Fichier audio"),
            horizontal=True,
        )
        file = (
            st.audio_input("Enregistrer la visite", key=f"mic-{wid}")
            if choice == "Microphone"
            else st.file_uploader("Importer un enregistrement", type=list(MIMES), key=f"file-{wid}")
        )
        if st.button(
            "Confirmer l’envoi à Groq", disabled=not file or cfg.APP_MODE != "live", type="primary"
        ):
            if file.size > cfg.MAX_AUDIO_SIZE_MB * 1_000_000:
                from src.domain.errors import AudioValidationError

                raise AudioValidationError("Enregistrement trop volumineux.")
            service = GroqTranscriptionService(cfg, runtime)
            with st.spinner("Transcription en cours…"):
                transcript = service.transcribe(file.name, file.getvalue(), file.type)
            wf.transcribe(w, transcript.text, transcript)
            st.rerun()
    if w.stage == Stage.NEW and w.note.source_type == "audio":
        return
    st.subheader("3 · Transcription")
    if w.transcription:
        t = w.transcription
        st.text(
            f"Langue : {t.language or 'non renvoyée'} · Durée audio : {t.duration if t.duration is not None else 'non renvoyée'}"
        )
    value = st.text_area(
        "Texte à analyser",
        w.note.text,
        key=f"text-{wid}",
        height=145,
        max_chars=cfg.MAX_TRANSCRIPT_CHARS,
    )
    changed = value != w.note.text
    if w.note.source_type == "demo" and cfg.APP_MODE == "demo":
        original = next(
            (e.text for e in examples() if e.name == repo.project(w.note.project_id).name), None
        )
        if original and original != value:

            def restore_example():
                st.session_state[f"text-{wid}"] = original
                wf.revise_text(w, original)

            st.button("Restaurer la note d’exemple", on_click=restore_example)
    if changed:
        wf.revise_text(w, value)
    if w.stage in (Stage.NEW, Stage.TRANSCRIBED):
        if changed and w.reports:
            st.warning(
                "Cette modification invalide la proposition en cours. Les révisions validées restent consultables."
            )
        if st.button("Confirmer la transcription corrigée", type="primary"):
            wf.approve(w)
            st.rerun()
        return
    if w.stage == Stage.TRANSCRIPT_APPROVED:
        st.subheader("4 · Analyse structurée")
        demo = cfg.APP_MODE == "demo"
        st.caption(
            "Extraction préenregistrée pour cette note."
            if demo
            else f"Envoi du texte approuvé à OpenAI · {cfg.OPENAI_MODEL} · facturation selon votre compte."
        )
        if st.button(
            "Charger la proposition" if demo else "Confirmer l’analyse OpenAI", type="primary"
        ):
            provider = DemoProvider() if demo else OpenAIExtractionService(cfg, runtime)
            with st.spinner("Préparation du compte rendu…"):
                wf.analyze(w, FieldIntelligencePipeline(provider, cfg))
            st.rerun()
    elif w.stage == Stage.IN_REVIEW:
        st.caption("5 · VALIDATION HUMAINE")
        review(repo, wf, w)
    elif w.stage in (Stage.VALIDATED, Stage.EXPORTED):
        st.subheader("6 · Rapport validé")
        downloads(repo, wf, w, w.reports[-1])
        st.button("Consulter les révisions", on_click=navigate, args=(3,))


def note_label(repo, w):
    return f"{repo.project(w.note.project_id).name} · {w.reference_datetime:%d/%m/%Y} · {str(w.note.id)[:6]}"


def downloads(repo, wf, w, r):
    c1, c2 = st.columns(2)
    callback = (
        wf.exported
        if r is w.reports[-1] and w.stage in (Stage.VALIDATED, Stage.EXPORTED)
        else "ignore"
    )
    args = (w,) if callable(callback) else ()
    prefix = f"orvane-{str(w.note.id)[:8]}-r{r.revision}"
    c1.download_button(
        "Télécharger le PDF",
        render_pdf(r, repo.project(r.project_id)),
        prefix + ".pdf",
        "application/pdf",
        on_click=callback,
        args=args,
    )
    c2.download_button(
        "Exporter le rapport JSON",
        r.model_dump_json(indent=2),
        prefix + ".json",
        "application/json",
        on_click=callback,
        args=args,
    )


def reports(repo, wf):
    st.title(NAV[3])
    options = [(w, r) for w in reversed(repo.data.works) for r in reversed(w.reports)]
    if not options:
        st.info("Les comptes rendus apparaîtront ici après la première analyse.")
        return
    by_id = {r.id: (w, r) for w, r in options}
    labels = {
        r.id: f"{note_label(repo, w)} · R{r.revision} · {'Validé' if r.status == 'validated' else 'Brouillon'}"
        for w, r in options
    }
    selected = st.selectbox("Compte rendu et révision", list(by_id), format_func=labels.__getitem__)
    w, r = by_id[selected]
    st.text(repo.project(r.project_id).name)
    st.text(r.extraction.summary)
    with st.expander("Détail du compte rendu"):
        from src.ui.editors import LABELS

        for section, label in LABELS.items():
            st.write(label)
            for item in getattr(r.extraction, section):
                st.text(getattr(item, "description", None) or item.question)
                st.caption("Citation source")
                st.text(item.source_excerpt)
    downloads(repo, wf, w, r)
    if r is w.reports[-1] and w.stage in (Stage.IN_REVIEW, Stage.VALIDATED, Stage.EXPORTED):
        with st.expander("Modifier cette révision"):
            review(repo, wf, w)


def action_plan(repo, wf):
    st.title(NAV[2])
    options = list(current_reports(repo))
    if not options:
        st.info("Validez un compte rendu pour alimenter le plan d’action.")
        return
    selected = st.selectbox(
        "Chantier",
        [None] + [p.id for p in repo.data.projects],
        format_func=lambda pid: repo.project(pid).name if pid else "Tous les chantiers",
    )
    reports = [(w, r) for w, r in options if selected is None or selected == r.project_id]
    items = [a for _, r in reports for a in r.extraction.actions]
    if not items:
        st.info("Aucune action validée pour cette sélection.")
        return
    items.sort(
        key=lambda a: (a.status.value == "Terminée", a.due_date or calendar_date.max, a.description)
    )
    projects = {
        a.id: repo.project(r.project_id).name for _, r in reports for a in r.extraction.actions
    }
    if any(w.stage not in (Stage.VALIDATED, Stage.EXPORTED) for w, r in reports):
        st.info("Les actions des notes en cours de révision se modifient dans Rapports.")
        st.button("Consulter les révisions", on_click=navigate, args=(3,))
    st.caption("Enregistrer le suivi crée une révision à valider pour chaque compte rendu modifié.")
    key = f"plan-{selected}-{len(repo.data.audit)}"
    with st.form(key):
        frame = editor("actions", items, key + "-actions", set(), True, projects)
        save = st.form_submit_button("Enregistrer le suivi", type="primary")
    if save:
        from src.domain.errors import InvalidWorkflowTransition
        from src.services.validation_service import integrity

        updates = {a.id: a for a in parse_rows("actions", frame)}
        pending = []
        for w, r in reports:
            candidate = r.extraction.model_copy(deep=True)
            candidate.actions = [updates[a.id] for a in r.extraction.actions]
            if candidate == r.extraction:
                continue
            if w.stage not in (Stage.VALIDATED, Stage.EXPORTED):
                raise InvalidWorkflowTransition(
                    "Un compte rendu modifié a déjà une révision en cours."
                )
            integrity(candidate, w.note.text)
            pending.append((w, candidate))
        for w, candidate in pending:
            wf.edit(w, candidate)
        if pending:
            st.rerun()
        st.info("Aucune modification à enregistrer.")


def quality(repo, runtime):
    st.title(NAV[4])
    edits, rate = corrections(repo)
    a, b, c = st.columns(3)
    a.metric("Appels de cette session", runtime.spent, border=True)
    b.metric("Corrections humaines", edits, border=True)
    c.metric("Propositions corrigées", "—" if rate is None else f"{rate:.0%}", border=True)
    if repo.data.metrics:
        st.subheader("Traitements mesurés")
        st.dataframe(
            [
                {
                    "Service": m.provider,
                    "Modèle": m.model,
                    "Durée (s)": round(m.duration_ms / 1000, 3),
                    "Tokens entrants": m.input_tokens,
                    "Tokens sortants": m.output_tokens,
                    "Résultat": m.error_type or "Réussi",
                }
                for m in repo.data.metrics
            ],
            hide_index=True,
        )
    else:
        st.info("Aucun appel fournisseur mesuré.")
    st.subheader("Évaluation annotée")
    st.caption(
        "Chargez le rapport produit par scripts/evaluate.py pour consulter les scores du modèle évalué."
    )
    from src.providers.demo_provider import DATA
    from src.services.evaluation_service import EvaluationReport

    with st.expander("Résultats hors ligne · cinq fixtures de démonstration"):
        replay = EvaluationReport.model_validate_json(
            (DATA / "evaluation/replay_report.json").read_bytes()
        )
        st.caption("Comparaison des fixtures avec leurs annotations. Aucun modèle appelé.")
        st.dataframe([replay.scores], hide_index=True)
    file = st.file_uploader("Rapport d’évaluation JSON", type=["json"])
    if file:
        if file.size > 2_000_000:
            st.error("Rapport d’évaluation trop volumineux.")
        else:
            result = EvaluationReport.model_validate_json(file.getvalue())
            st.text(result.model + " · " + result.prompt_version)
            st.dataframe([result.scores], hide_index=True)
    if repo.data.audit:
        with st.expander("Journal des modifications"):
            st.dataframe(
                [
                    {
                        "Date": e.timestamp,
                        "Événement": e.event_type,
                        "Élément": str(e.entity_id),
                        "Avant": e.before,
                        "Après": e.after,
                    }
                    for e in repo.data.audit
                ],
                hide_index=True,
            )
