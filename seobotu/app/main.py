from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
import os

from app.core.config import settings
from app.services.dataforseo_client import dataforseo
from app.services.site_analyzer import site_analyzer
from app.services.report_generator import report_generator
from app.services.pdf_builder import pdf_builder

app = FastAPI(title=settings.PROJECT_NAME)

class AuditRequest(BaseModel):
    target_url: str
    email: str
    sector: Optional[str] = "auto" # default

def run_audit_workflow(target_url: str, email: str, sector: str):
    print(f"Starting audit for {target_url}...")
    
    # 1. Fetch SERP Data
    # For demonstration, we'll fetch just one keyword's data to simulate
    serp_result = dataforseo.fetch_serp("205 55 r16 lastik fiyatları", target_url)
    
    # 2. Site Analysis
    site_data = site_analyzer.analyze_url(target_url)
    
    # 3. Generate Report Context
    report_data = report_generator.generate_full_report(target_url, [serp_result], site_data)
    
    # 4. Build PDF
    import time
    output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
    os.makedirs(output_dir, exist_ok=True)
    domain = target_url.replace("https://", "").replace("http://", "").replace("www.", "").split('/')[0]
    timestamp = int(time.time())
    pdf_path = os.path.join(output_dir, f"{domain}_seo_audit_{timestamp}.pdf")
    
    pdf_builder.create_pdf(report_data, pdf_path)
    
    print(f"Audit completed! PDF saved to {pdf_path}")
    # Here an email service would send the pdf to `email`
    
@app.get("/")
def read_root():
    return {"message": "SEO Audit Bot API is running."}

@app.post("/api/v1/audit")
def start_audit(request: AuditRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_audit_workflow, request.target_url, request.email, request.sector)
    return {
        "status": "success",
        "message": f"Audit started for {request.target_url}. Report will be sent to {request.email}."
    }

