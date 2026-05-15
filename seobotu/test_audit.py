import requests
import time
import os
import glob

url = "http://127.0.0.1:8000/api/v1/audit"
data = {
    "target_url": "https://www.lastikborsasi.com",
    "email": "test@example.com",
    "sector": "auto"
}

try:
    print("Triggering audit...")
    response = requests.post(url, json=data)
    print(response.json())
    
    # Wait for background task to finish (Gemini API takes 20-40 seconds for 4 long prompts)
    print("Waiting up to 60 seconds for PDF generation...")
    
    pdf_found = False
    for i in range(12):
        time.sleep(5)
        # Check for new PDFs in outputs dir
        pdfs = glob.glob("outputs/lastikborsasi.com_seo_audit_*.pdf")
        if pdfs:
            print(f"Success! PDF file generated: {pdfs[-1]}")
            pdf_found = True
            break
        print(f"Waiting... ({i*5+5}s)")
        
    if not pdf_found:
        print("PDF file not found after 60 seconds.")
except Exception as e:
    print(f"Error: {e}")
