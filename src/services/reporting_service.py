from io import BytesIO
from itertools import zip_longest
from textwrap import wrap
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

NAVY = colors.HexColor("#172554")
MUTED = colors.HexColor("#475569")
BLUE = colors.HexColor("#2563EB")


def paragraph(text, size=10, bold=False, color=None):
    safe = escape(str(text) if text is not None else "Non précisé").replace("\n", "<br/>")
    return Paragraph(
        safe,
        ParagraphStyle(
            "body",
            fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=size,
            leading=size * 1.45,
            textColor=color or NAVY,
            alignment=TA_LEFT,
            splitLongWords=True,
            spaceAfter=3,
        ),
    )


def render_pdf(report, project):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=19 * mm,
        rightMargin=19 * mm,
        topMargin=28 * mm,
        bottomMargin=20 * mm,
        title="Compte rendu de chantier",
        author="ORVANE",
        invariant=1,
    )
    state = "VALIDÉ" if report.status == "validated" else "BROUILLON"
    local = ZoneInfo(project.reference_timezone)

    def as_date(value):
        return value.astimezone(local).strftime("%d/%m/%Y à %H:%M")

    content = [
        paragraph("Compte rendu de chantier", 24, True),
        paragraph(project.name, 16, True),
        paragraph(
            project.location
            + "  |  "
            + as_date(report.created_at)
            + "  |  Révision "
            + str(report.revision)
        ),
        paragraph(
            f"{state} · {as_date(report.validated_at)}" if report.validated_at else state,
            9,
            True,
            BLUE,
        ),
    ]

    if report.reference_datetime:
        content.append(
            paragraph(
                "Date de visite · "
                + report.reference_datetime.astimezone(local).strftime("%d/%m/%Y")
            )
        )

    def section(title, items):
        content.append(Spacer(1, 9))
        heading = paragraph(title, 13, True)
        heading.keepWithNext = True
        content.append(heading)
        content.extend(paragraph(item) for item in (items or ["Aucun élément consigné."]))

    data = report.extraction
    section("Synthèse opérationnelle", [data.summary])
    section(
        "Avancement",
        [
            f"{o.work_status} · {o.description}"
            for o in data.observations
            if o.category == "Avancement"
        ],
    )
    section(
        "Observations et risques",
        [
            f"{o.category} · {o.description}"
            for o in data.observations
            if o.category != "Avancement"
        ],
    )
    section(
        "Problèmes",
        [
            f"{i.title} ({i.severity or 'gravité non précisée'} · {'ouvert' if i.is_open else 'clos'}). {i.description} Impact : {i.operational_impact or 'non précisé'}."
            for i in data.issues
        ],
    )
    section("Décisions", [i.description for i in data.decisions])
    if data.actions:
        content.extend([Spacer(1, 9), paragraph("Plan d’action", 13, True)])
        rows = [
            [
                paragraph(t, 9, True, colors.white)
                for t in ("Action", "Responsable", "Échéance", "Priorité / statut")
            ]
        ]
        for a in data.actions:
            cells = (
                a.description,
                a.assignee or "Non précisé",
                a.due_date.strftime("%d/%m/%Y") if a.due_date else "Non précisée",
                f"{a.priority or 'Non précisée'} / {a.status}",
            )
            chunks = [
                wrap(value, width=limit)
                for value, limit in zip(cells, (640, 240, 180, 260), strict=True)
            ]
            for part in zip_longest(*chunks, fillvalue=""):
                rows.append([paragraph(cell, 9) for cell in part])
        table = LongTable(
            rows,
            colWidths=[doc.width * f for f in (0.43, 0.18, 0.17, 0.22)],
            repeatRows=1,
            splitInRow=1,
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F1F5F9")],
                    ),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        content.append(table)
    else:
        section("Plan d’action", [])
    section(
        "Informations à clarifier",
        [c.question + " " + c.reason for c in data.clarifications]
        + [
            item.description
            for group in (data.actions, data.observations, data.issues, data.decisions)
            for item in group
            if item.requires_review
        ],
    )

    evidence = [
        f"{label} {index} · « {item.source_excerpt} »"
        for label, items in (
            ("Action", data.actions),
            ("Observation", data.observations),
            ("Problème", data.issues),
            ("Décision", data.decisions),
        )
        for index, item in enumerate(items, 1)
    ]
    if evidence:
        section("Extraits de la note", evidence)

    def furniture(canvas, document):
        width, height = A4
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(19 * mm, height - 17 * mm, "ORVANE")
        canvas.setStrokeColor(BLUE)
        canvas.line(19 * mm, height - 20 * mm, width - 19 * mm, height - 20 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(
            19 * mm, 12 * mm, f"Compte rendu de chantier  /  {state}  /  R{report.revision}"
        )
        canvas.drawRightString(width - 19 * mm, 12 * mm, f"Page {document.page}")

    doc.build(content, onFirstPage=furniture, onLaterPages=furniture)
    return buffer.getvalue()
