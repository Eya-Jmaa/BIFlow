"""Run reports.

Every export is built from one assembled report, so JSON, Excel and PDF cannot
drift apart or disagree about a number. The report carries the full set of
deliverables for a run — data quality, transformation lineage, the semantic
model, the KPI catalogue with formulas and SQL, insights with their
recommendations, per-agent evaluation and the XAI explanations — rather than
just the headline figures.

CSV is the exception: it is a single flat table, so it carries the KPI
catalogue alone. Use JSON or Excel for the complete report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    AuditEvent,
    DataProfile,
    DataQualityIssue,
    DataQualityReport,
    Dataset,
    Dimension,
    EvaluationResult,
    Insight,
    KPI,
    KPIResult,
    Measure,
    PipelineRun,
    Project,
    Relationship,
    SemanticModel,
    Transformation,
    XAIExplanation,
)

router = APIRouter()


def _latest(db: Session, project_id: UUID) -> PipelineRun:
    run = (
        db.query(PipelineRun)
        .filter(PipelineRun.project_id == project_id)
        .order_by(PipelineRun.created_at.desc())
        .first()
    )
    if not run:
        raise HTTPException(404, "No pipeline run found")
    return run


def build_report(db: Session, project_id: UUID) -> dict[str, Any]:
    """Assemble the complete report for a project's latest run."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    run = _latest(db, project_id)

    kpis = db.query(KPI).filter(KPI.run_id == run.id).all()
    results = {
        result.kpi_id: result
        for result in db.query(KPIResult).filter(KPIResult.run_id == run.id).all()
    }
    quality_reports = db.query(DataQualityReport).filter(DataQualityReport.run_id == run.id).all()
    model = db.query(SemanticModel).filter(SemanticModel.run_id == run.id).first()
    events = db.query(AuditEvent).filter(AuditEvent.run_id == run.id).all()
    verdict = next((e for e in events if e.event_type == "run_verdict"), None)

    return {
        "project": {
            "name": project.name,
            "objective": project.business_objective,
            "domain": project.domain,
            "status": project.status,
        },
        "run": {
            "id": str(run.id),
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "engine": run.llm_model or "deterministic only",
            "agent_versions": run.agent_versions,
        },
        "generated_at": datetime.now(timezone.utc),
        "datasets": [
            {
                "name": dataset.name,
                "table": dataset.table_name,
                "source_type": dataset.source_type,
                "rows": dataset.row_count,
                "columns": dataset.column_count,
                "layer": dataset.layer,
            }
            for dataset in db.query(Dataset).filter(Dataset.project_id == project_id).all()
        ],
        # ── Deliverable: Data Quality Report ──────────────────────────
        "data_quality": [
            {
                "overall_score": report.overall_score,
                "completeness": report.completeness,
                "uniqueness": report.uniqueness,
                "consistency": report.consistency,
                "validity": report.validity,
                "referential_integrity": report.referential_integrity,
                "issues": [
                    {
                        "severity": issue.severity,
                        "type": issue.issue_type,
                        "table": issue.table_name,
                        "column": issue.column_name,
                        "rows_affected": issue.rows_affected,
                        "detection_method": issue.detection_method,
                        "recommended_action": issue.recommended_action,
                        "status": issue.status,
                    }
                    for issue in db.query(DataQualityIssue)
                    .filter(DataQualityIssue.report_id == report.id)
                    .all()
                ],
            }
            for report in quality_reports
        ],
        "profiling": [
            {
                "table": (db.get(Dataset, profile.dataset_id).table_name
                          if db.get(Dataset, profile.dataset_id) else None),
                "rows": profile.row_count,
                "columns": profile.column_count,
                "quality_score": profile.quality_score,
                "duplicate_rows": profile.duplicate_row_count,
                "warnings": profile.warnings,
                "pii_flags": profile.pii_flags,
            }
            for profile in db.query(DataProfile).filter(DataProfile.run_id == run.id).all()
        ],
        "transformations": [
            {
                "operation": item.operation,
                "table": item.table_name,
                "column": item.column_name,
                "rows_affected": item.rows_affected,
                "reason": item.reason,
                "before_example": item.before_example,
                "after_example": item.after_example,
            }
            for item in db.query(Transformation).filter(Transformation.run_id == run.id).all()
        ],
        "semantic_model": None
        if model is None
        else {
            "domain": model.domain,
            "version": model.version,
            "summary": model.summary,
            "grain": model.grain,
            "dimensions": [
                {"name": d.name, "type": d.dim_type, "grain": d.grain}
                for d in db.query(Dimension).filter(Dimension.semantic_model_id == model.id).all()
            ],
            "measures": [
                {"name": m.name, "aggregation": m.aggregation, "unit": m.unit}
                for m in db.query(Measure).filter(Measure.semantic_model_id == model.id).all()
            ],
            "relationships": [
                {
                    "source": f"{r.source_table}.{r.source_column}",
                    "target": f"{r.target_table}.{r.target_column}",
                    "cardinality": r.cardinality,
                    "confidence": r.confidence,
                    "validated": r.validated,
                    "overlap_ratio": r.overlap_ratio,
                }
                for r in db.query(Relationship)
                .filter(Relationship.semantic_model_id == model.id)
                .all()
            ],
        },
        # ── Deliverable: KPI catalogue and formulas ───────────────────
        "kpis": [
            {
                "name": kpi.name,
                "description": kpi.description,
                "business_meaning": kpi.business_meaning,
                "formula": kpi.formula,
                "sql": kpi.query_sql,
                "unit": kpi.unit,
                "status": kpi.validation_status,
                "confidence": kpi.confidence,
                "value": results[kpi.id].value if kpi.id in results else None,
                "previous_value": results[kpi.id].previous_value if kpi.id in results else None,
                "change_pct": results[kpi.id].change_pct if kpi.id in results else None,
                "source_tables": kpi.data_sources,
                "provenance": kpi.filters,
            }
            for kpi in kpis
        ],
        # ── Deliverable: insights and recommendations ─────────────────
        "insights": [
            {
                "title": insight.title,
                "category": insight.category,
                "severity": insight.severity,
                "description": insight.description,
                "recommendation": insight.recommendation,
                "recommendation_basis": insight.recommendation_basis,
                "metric": insight.metric,
                "value": insight.value,
                "comparison": insight.comparison,
                "period": insight.period,
                "confidence": insight.confidence,
                "grounded": insight.grounded,
                "evidence": insight.evidence,
                "sql": insight.query_sql,
            }
            for insight in db.query(Insight).filter(Insight.run_id == run.id).all()
        ],
        # ── Deliverable: evaluation report ────────────────────────────
        "evaluation": [
            {
                "agent": row.agent_name,
                "metric": row.metric_name,
                "score": row.score,
                "details": row.details,
            }
            for row in db.query(EvaluationResult).filter(EvaluationResult.run_id == run.id).all()
        ],
        # ── Deliverable: XAI ──────────────────────────────────────────
        "audit": {
            "verdict": None
            if verdict is None
            else {
                "status": verdict.status,
                "message": verdict.message,
                "details": verdict.details,
            },
            "checks": [
                {
                    "type": event.event_type,
                    "entity": event.entity_type,
                    "status": event.status,
                    "message": event.message,
                }
                for event in events
                if event.event_type != "run_verdict"
            ],
        },
        "xai": [
            {
                "entity_type": x.entity_type,
                "what_happened": x.what_happened,
                "how_calculated": x.how_calculated,
                "data_used": x.data_used,
                "kpi_relevance": x.kpi_relevance,
                "assumptions": x.assumptions,
                "quality_limitations": x.quality_limitations,
                "transformations": x.transformations,
                "producer_agent": x.producer_agent,
                "validator_agent": x.validator_agent,
            }
            for x in db.query(XAIExplanation).filter(XAIExplanation.run_id == run.id).all()
        ],
    }


@router.get("/projects/{project_id}/export/json")
def export_json(project_id: UUID, db: Session = Depends(get_db)):
    """The complete report, every section."""
    return build_report(db, project_id)


@router.get("/projects/{project_id}/export/csv")
def export_csv(project_id: UUID, db: Session = Depends(get_db)):
    """The KPI catalogue as a flat table — CSV cannot carry the other sections."""
    import csv
    import io

    report = build_report(db, project_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["name", "value", "unit", "change_pct", "status", "formula", "sql", "business_meaning"]
    )
    for kpi in report["kpis"]:
        writer.writerow(
            [
                kpi["name"],
                kpi["value"],
                kpi["unit"] or "",
                kpi["change_pct"] if kpi["change_pct"] is not None else "",
                kpi["status"],
                kpi["formula"],
                kpi["sql"] or "",
                kpi["business_meaning"],
            ]
        )
    data = buffer.getvalue().encode("utf-8-sig")  # BOM so Excel reads UTF-8
    return StreamingResponse(
        BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=biflow-kpi-catalogue.csv"},
    )


@router.get("/projects/{project_id}/export/xlsx")
def export_xlsx(project_id: UUID, db: Session = Depends(get_db)):
    """One workbook, one sheet per deliverable."""
    import xlsxwriter

    report = build_report(db, project_id)
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    header = workbook.add_format({"bold": True, "bg_color": "#EEF0FE", "border": 1})
    wrap = workbook.add_format({"text_wrap": True, "valign": "top"})

    def sheet(name: str, columns: list[str], rows: list[list[Any]], widths: list[int]) -> None:
        worksheet = workbook.add_worksheet(name[:31])
        worksheet.write_row(0, 0, columns, header)
        worksheet.freeze_panes(1, 0)
        for index, width in enumerate(widths):
            worksheet.set_column(index, index, width, wrap if width > 40 else None)
        for row_index, row in enumerate(rows, start=1):
            worksheet.write_row(row_index, 0, ["" if v is None else v for v in row])

    sheet(
        "Summary",
        ["Field", "Value"],
        [
            ["Project", report["project"]["name"]],
            ["Objective", report["project"]["objective"]],
            ["Domain", report["project"]["domain"]],
            ["Run", report["run"]["id"]],
            ["Status", report["run"]["status"]],
            ["Engine", report["run"]["engine"]],
            ["Generated", str(report["generated_at"])],
            ["Verdict", (report["audit"]["verdict"] or {}).get("status", "n/a")],
            ["Verdict reason", (report["audit"]["verdict"] or {}).get("message", "")],
        ],
        [20, 90],
    )
    sheet(
        "KPI catalogue",
        ["Name", "Value", "Unit", "Change %", "Status", "Formula", "SQL", "Meaning"],
        [
            [
                k["name"], k["value"], k["unit"], k["change_pct"], k["status"],
                k["formula"], k["sql"], k["business_meaning"],
            ]
            for k in report["kpis"]
        ],
        [26, 16, 10, 12, 16, 60, 70, 60],
    )
    sheet(
        "Data quality",
        ["Severity", "Issue", "Table", "Column", "Rows", "Detection", "Recommended action"],
        [
            [
                i["severity"], i["type"], i["table"], i["column"],
                i["rows_affected"], i["detection_method"], i["recommended_action"],
            ]
            for report_block in report["data_quality"]
            for i in report_block["issues"]
        ],
        [12, 22, 18, 18, 12, 26, 70],
    )
    sheet(
        "Quality scores",
        ["Overall", "Completeness", "Uniqueness", "Consistency", "Validity", "Referential"],
        [
            [
                b["overall_score"], b["completeness"], b["uniqueness"],
                b["consistency"], b["validity"], b["referential_integrity"],
            ]
            for b in report["data_quality"]
        ],
        [12, 14, 12, 13, 11, 13],
    )
    sheet(
        "Transformations",
        ["Operation", "Table", "Column", "Rows", "Before", "After", "Reason"],
        [
            [t["operation"], t["table"], t["column"], t["rows_affected"],
             t["before_example"], t["after_example"], t["reason"]]
            for t in report["transformations"]
        ],
        [20, 18, 18, 12, 26, 26, 60],
    )
    sheet(
        "Insights",
        ["Category", "Severity", "Title", "Description", "Recommendation", "Basis", "Grounded"],
        [
            [
                i["category"], i["severity"], i["title"], i["description"],
                i["recommendation"] or "", i["recommendation_basis"] or "",
                "yes" if i["grounded"] else "no",
            ]
            for i in report["insights"]
        ],
        [14, 11, 50, 70, 80, 30, 10],
    )
    sheet(
        "Evaluation",
        ["Agent", "Metric", "Score"],
        [[e["agent"], e["metric"], e["score"]] for e in report["evaluation"]],
        [16, 30, 10],
    )
    sheet(
        "XAI",
        ["What happened", "How calculated", "Data used", "Assumptions", "Limitations", "Agents"],
        [
            [
                x["what_happened"], x["how_calculated"], x["data_used"],
                x["assumptions"], x["quality_limitations"],
                f"{x['producer_agent']} → {x['validator_agent']}",
            ]
            for x in report["xai"]
        ],
        [50, 80, 26, 80, 80, 22],
    )
    if report["semantic_model"]:
        model = report["semantic_model"]
        sheet(
            "Semantic model",
            ["Kind", "Name", "Detail"],
            [["dimension", d["name"], d["type"]] for d in model["dimensions"]]
            + [["measure", m["name"], m["aggregation"]] for m in model["measures"]]
            + [
                ["relationship", f"{r['source']} → {r['target']}", r["cardinality"]]
                for r in model["relationships"]
            ],
            [16, 44, 24],
        )

    workbook.close()
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=biflow-report.xlsx"},
    )


@router.get("/projects/{project_id}/export/pdf")
def export_pdf(project_id: UUID, db: Session = Depends(get_db)):
    """A readable report: verdict first, then quality, KPIs, findings, XAI."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.lib import colors

    report = build_report(db, project_id)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"BIFlow report — {report['project']['name']}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=17, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=8.5, leading=12)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, textColor=colors.HexColor("#555"))
    mono = ParagraphStyle("mono", parent=body, fontName="Courier", fontSize=6.8, leading=9)

    def table(columns: list[str], rows: list[list[str]], widths: list[float]):
        data = [[Paragraph(f"<b>{c}</b>", small) for c in columns]] + [
            [Paragraph(str(cell) if cell is not None else "", small) for cell in row]
            for row in rows
        ]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF0FE")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D4D8E6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return t

    width = doc.width
    story: list[Any] = []

    story.append(Paragraph(f"BIFlow report — {report['project']['name']}", h1))
    story.append(Paragraph(report["project"]["objective"], body))
    story.append(
        Paragraph(
            f"Domain {report['project']['domain']} · run {report['run']['id'][:8]} · "
            f"engine {report['run']['engine']} · generated {report['generated_at']:%Y-%m-%d %H:%M}",
            small,
        )
    )

    verdict = report["audit"]["verdict"]
    if verdict:
        story.append(Paragraph("Audit verdict", h2))
        story.append(Paragraph(f"<b>{verdict['status']}</b> — {verdict['message']}", body))
        for caveat in (verdict.get("details") or {}).get("caveats", [])[:6]:
            story.append(Paragraph(f"• {caveat}", small))

    for block in report["data_quality"]:
        story.append(Paragraph("Data quality", h2))
        story.append(
            table(
                ["Overall", "Complete", "Unique", "Consistent", "Valid", "Referential"],
                [[
                    block["overall_score"], block["completeness"], block["uniqueness"],
                    block["consistency"], block["validity"], block["referential_integrity"],
                ]],
                [width / 6] * 6,
            )
        )
        if block["issues"]:
            story.append(Spacer(1, 6))
            story.append(
                table(
                    ["Sev", "Issue", "Column", "Rows", "Recommended action"],
                    [
                        [i["severity"], i["type"], i["column"] or "—",
                         f"{i['rows_affected']:,}" if i["rows_affected"] else "—",
                         i["recommended_action"]]
                        for i in block["issues"]
                    ],
                    [width * 0.08, width * 0.17, width * 0.15, width * 0.10, width * 0.50],
                )
            )

    if report["transformations"]:
        story.append(Paragraph("Transformations applied", h2))
        story.append(
            table(
                ["Operation", "Target", "Rows", "Reason"],
                [
                    [t["operation"], f"{t['table']}.{t['column']}" if t["column"] else t["table"],
                     f"{t['rows_affected']:,}", t["reason"]]
                    for t in report["transformations"]
                ],
                [width * 0.18, width * 0.24, width * 0.12, width * 0.46],
            )
        )

    story.append(PageBreak())
    story.append(Paragraph("KPI catalogue", h2))
    for kpi in report["kpis"]:
        value = kpi["value"]
        shown = f"{value:,.2f}" if isinstance(value, (int, float)) else "n/a"
        story.append(Paragraph(f"<b>{kpi['name']}</b> — {shown} {kpi['unit'] or ''}", body))
        story.append(Paragraph(kpi["business_meaning"], small))
        story.append(Paragraph(kpi["formula"], mono))
        if kpi["sql"]:
            story.append(Paragraph(kpi["sql"], mono))
        story.append(Spacer(1, 5))

    story.append(PageBreak())
    story.append(Paragraph("Insights and recommendations", h2))
    for insight in report["insights"]:
        story.append(
            Paragraph(f"<b>[{insight['category']}] {insight['title']}</b>", body)
        )
        story.append(Paragraph(insight["description"], small))
        if insight["recommendation"]:
            story.append(
                Paragraph(f"<b>Recommendation:</b> {insight['recommendation']}", body)
            )
            story.append(Paragraph(f"Rule: {insight['recommendation_basis']}", small))
        story.append(Spacer(1, 6))

    if report["evaluation"]:
        story.append(Paragraph("Agent evaluation", h2))
        story.append(
            table(
                ["Agent", "Metric", "Score"],
                [
                    [e["agent"], e["metric"].replace("_", " "), f"{e['score']:.3f}"]
                    for e in report["evaluation"]
                ],
                [width * 0.22, width * 0.56, width * 0.22],
            )
        )

    if report["xai"]:
        story.append(Paragraph("Explanations (XAI)", h2))
        for x in report["xai"][:20]:
            story.append(Paragraph(f"<b>{x['what_happened']}</b>", body))
            story.append(Paragraph(x["how_calculated"], small))
            story.append(Paragraph(f"Assumptions: {x['assumptions']}", small))
            story.append(
                Paragraph(f"Limitations: {x['quality_limitations']}", small)
            )
            story.append(Spacer(1, 6))

    doc.build(story)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=biflow-report.pdf"},
    )
