import os
import markdown
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

class PDFBuilder:
    def __init__(self):
        self.template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
        self.env = Environment(loader=FileSystemLoader(self.template_dir))
        
    def create_pdf(self, report_data: dict, output_path: str):
        """
        Parses Markdown to HTML, renders the Jinja template, and converts it to PDF using Playwright.
        """
        # Convert Markdown to HTML using the python-markdown library
        # extensions: tables (for markdown tables), fenced_code (for code blocks)
        md_content = report_data.get("markdown_content", "")
        html_from_md = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
        
        # Inject the HTML content into the report_data context
        report_data["html_content"] = html_from_md
        
        # Render the full template
        template = self.env.get_template('report_template.html')
        full_html_content = template.render(**report_data)
        
        # Save HTML temporarily (useful for debugging)
        temp_html_path = output_path.replace('.pdf', '.html')
        with open(temp_html_path, 'w', encoding='utf-8') as f:
            f.write(full_html_content)
            
        # Use Playwright to generate PDF
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Use set_content to load the HTML directly
            page.set_content(full_html_content, wait_until="networkidle")
            
            # Print to PDF with book-style settings
            page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
                margin={"top": "40px", "right": "40px", "bottom": "40px", "left": "40px"},
                display_header_footer=True,
                header_template='<div style="font-size: 8px; margin-left: 40px; color: #7f8c8d;">SEO Audit Raporu - Gizli ve Özel</div>',
                footer_template='<div style="font-size: 8px; margin: 0 auto; color: #7f8c8d;">Sayfa <span class="pageNumber"></span> / <span class="totalPages"></span></div>'
            )
            browser.close()
            
        print(f"Comprehensive PDF successfully created at {output_path}")
        return output_path

pdf_builder = PDFBuilder()
