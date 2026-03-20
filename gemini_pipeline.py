import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
import pypdf
import convert_to_csv

# Load environment variables (useful for GOOGLE_API_KEY)
load_dotenv()

# --- Configuration ---
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_ID = "gemini-3-flash-preview"

INPUT_PDF = Path("input/AHA_1966_sample.pdf")
GEMINI_OUTPUT_DIR = Path("output/gemini_run")
MARKDOWN_OUTPUT_DIR = GEMINI_OUTPUT_DIR / "markdown"
CSV_OUTPUT_DIR = GEMINI_OUTPUT_DIR / "csv"
TEMP_PAGE_DIR = Path("output/temp_pages")

SYSTEM_PROMPT = """Convert the following document to markdown.
Return only the markdown with no explanation text. Do not include delimiters like ```markdown or ```html.

RULES:
  - You can exclude page headers and footers, but do not omit any table information. 
  - Return tables in an HTML format.
  - USE THESE EXACT COLUMN HEADERS for every table:
    "Hospital, Address, Telephone, Administrator, Approval and Facility Codes", "control", "service", "stay", "beds", "admissions", "census", "bassinets", "births", "newborn census", "total", "payroll", "personnel", "city", "county"
  - Charts & infographics must be interpreted to a markdown format. Prefer table format when applicable.
  - Add the city and county for each hospital as fields to the table rather than header rows for sections. 
"""

def setup_client():
    if not API_KEY:
        print("Error: GOOGLE_API_KEY not found in environment or .env file.")
        sys.exit(1)
    return genai.Client(api_key=API_KEY)

def upload_and_process_pdf(client, path: Path):
    """Uploads to File API and waits for ACTIVE state."""
    print(f"  Uploading {path.name}...")
    file = client.files.upload(file=str(path))
    
    while file.state.name == "PROCESSING":
        time.sleep(1)
        file = client.files.get(name=file.name)
        
    if file.state.name != "ACTIVE":
        raise Exception(f"File {file.name} failed to process. State: {file.state.name}")
    
    return file

def run_ocr_on_page(client, file, page_num):
    """Generates markdown for a single page."""
    print(f"  Running OCR on page {page_num}...")
    
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=[file, f"Process page {page_num} according to your system instructions."],
        config={
            "system_instruction": SYSTEM_PROMPT,
            "temperature": 0.0
        }
    )
    return response.text

def main():
    client = setup_client()
    
    # Ensure directories exist
    MARKDOWN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CSV_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_PAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    if not INPUT_PDF.exists():
        print(f"Error: Input file {INPUT_PDF} not found.")
        return

    reader = pypdf.PdfReader(str(INPUT_PDF))
    total_pages = len(reader.pages)
    print(f"Found {total_pages} pages in PDF.")

    all_markdown_content = ""

    for i in range(total_pages):
        print(f"Processing Page {i+1}/{total_pages}...")
        
        # 1. Create a single-page PDF
        page_pdf_path = TEMP_PAGE_DIR / f"page_{i+1}.pdf"
        writer = pypdf.PdfWriter()
        writer.add_page(reader.pages[i])
        with open(page_pdf_path, "wb") as f:
            writer.write(f)
            
        try:
            # 2. Upload and OCR
            pdf_file = upload_and_process_pdf(client, page_pdf_path)
            markdown_text = run_ocr_on_page(client, pdf_file, i+1)
            
            # 3. Save individual MD file
            md_path = MARKDOWN_OUTPUT_DIR / f"page_{i+1}.md"
            md_path.write_text(markdown_text, encoding="utf-8")
            print(f"  Saved markdown to {md_path}")
            
            all_markdown_content += markdown_text + "\n\n"
            
        except Exception as e:
            print(f"  Error on page {i+1}: {e}")
        finally:
            # Cleanup local temp file
            if page_pdf_path.exists():
                page_pdf_path.unlink()

    # Save a combined MD file
    combined_md = MARKDOWN_OUTPUT_DIR / "combined_gemini_output.md"
    combined_md.write_text(all_markdown_content, encoding="utf-8")
    print(f"\nCombined markdown saved to {combined_md}")

    # Now run conversion
    print("\nConverting markdown tables to CSV...")
    try:
        # Override defaults in convert_to_csv
        convert_to_csv.MARKDOWN_FILE = combined_md
        convert_to_csv.OUTPUT_DIR = CSV_OUTPUT_DIR
        convert_to_csv.main()
        print(f"Pipeline finished successfully. Results in {GEMINI_OUTPUT_DIR}")
    except Exception as e:
        print(f"Error during CSV conversion: {e}")

if __name__ == "__main__":
    main()
