from __future__ import annotations

import json
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Insight, KPI, KPIResult, PipelineRun, Project

router = APIRouter()


def _latest(db: Session, project_id: UUID) -> PipelineRun:
    run = db.query(PipelineRun).filter(PipelineRun.project_id == project_id).order_by(PipelineRun.created_at.desc()).first()
    if not run:
        raise HTTPException(404, "No pipeline run found")
    return run


@router.get("/projects/{project_id}/export/json")
def export_json(project_id: UUID, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    run = _latest(db, project_id)
    kpis = db.query(KPI).filter(KPI.run_id == run.id).all()
    insights = db.query(Insight).filter(Insight.run_id == run.id).all()
    payload = {
        "project": {"name": project.name, "objective": project.business_objective, "domain": project.domain},
        "run_id": str(run.id),
        "timestamp": run.completed_at or run.created_at,
        "kpis": [
            {
                "name": k.name,
                "formula": k.formula,
                "sql": k.query_sql,
                "status": k.validation_status,
                "value": (db.query(KPIResult).filter(KPIResult.kpi_id == k.id).first() or KPIResult()).value
                if False
                else (res.value if (res := db.query(KPIResult).filter(KPIResult.kpi_id == k.id).first()) else None),
            }
            for k in kpis
        ],
        "insights": [{"title": i.title, "description": i.description, "evidence": i.evidence} for i in insights],
    }
    return payload


@router.get("/projects/{project_id}/export/csv")
def export_csv(project_id: UUID, db: Session = Depends(get_db)):
    run = _latest(db, project_id)
    kpis = db.query(KPI).filter(KPI.run_id == run.id).all()
    lines = ["name,formula,value,status"]
    for k in kpis:
        res = db.query(KPIResult).filter(KPIResult.kpi_id == k.id).first()
        value = res.value if res else ""
        lines.append(f"\"{k.name}\",\"{k.formula}\",{value},{k.validation_status}")
    data = "\n".join(lines).encode("utf-8")
    return StreamingResponse(BytesIO(data), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=kpis.csv"})


@router.get("/projects/{project_id}/export/xlsx")
def export_xlsx(project_id: UUID, db: Session = Depends(get_db)):
    import xlsxwriter

    run = _latest(db, project_id)
    kpis = db.query(KPI).filter(KPI.run_id == run.id).all()
    insights = db.query(Insight).filter(Insight.run_id == run.id).all()
    bio = BytesIO()
    wb = xlsxwriter.Workbook(bio, {"in_memory": True})
    kpi_sheet = wb.add_worksheet("KPIs")
    kpi_sheet.write_row(0, 0, ["Name", "Formula", "SQL", "Value", "Status"])
    for idx, k in enumerate(kpis, start=1):
        res = db.query(KPIResult).filter(KPIResult.kpi_id == k.id).first()
        kpi_sheet.write_row(idx, 0, [k.name, k.formula, k.query_sql or "", res.value if res else None, k.validation_status])
    insight_sheet = wb.add_worksheet("Insights")
    insight_sheet.write_row(0, 0, ["Title", "Category", "Description", "Value"])
    for idx, i in enumerate(insights, start=1):
        insight_sheet.write_row(idx, 0, [i.title, i.category, i.description, i.value])
    wb.close()
    bio.seek(0)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=biflow-report.xlsx"},
    )


@router.get("/projects/{project_id}/export/pdf")
def export_pdf(project_id: UUID, db: Session = Depends(get_db)):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    project = db.get(Project, project_id)
    run = _latest(db, project_id)
    kpis = db.query(KPI).filter(KPI.run_id == run.id).all()
    insights = db.query(Insight).filter(Insight.run_id == run.id).all()
    bio = BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, f"BIFlow report — {project.name}")
    y -= 24
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Objective: {project.business_objective[:120]}")
    y -= 16
    c.drawString(40, y, f"Run: {run.id}  Status: {run.status}")
    y -= 28
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "KPIs")
    y -= 18
    c.setFont("Helvetica", 9)
    for k in kpis:
        res = db.query(KPIResult).filter(KPIResult.kpi_id == k.id).first()
        line = f"{k.name}: {res.value if res else 'n/a'}  [{k.formula}]"
        c.drawString(40, y, line[:110])
        y -= 14
        if y < 80:
            c.showPage()
            y = height - 50
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Insights")
    y -= 18
    c.setFont("Helvetica", 9)
    for i in insights:
        c.drawString(40, y, f"- {i.title[:110]}")
        y -= 14
        if y < 80:
            c.showPage()
            y = height - 50
    c.save()
    bio.seek(0)
    return StreamingResponse(bio, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=biflow-report.pdf"})
