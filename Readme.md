```markdown
# PDF Barcode Validation Toolkit
Lightweight utilities for validating PDF batches that contain main and supplementary barcode pages.

## Requirements
- Python 3.10+
- Dependencies: pymupdf (fitz), pillow, zxing-cpp, opencv-python, pandas, numpy
- Works on Windows

### Install
```bash
pip install pymupdf pillow zxing-cpp opencv-python pandas numpy
```

## How It Works
- Reads all PDFs in a target folder (default: current directory)
- Derives the expected barcode from the PDF filename
- Scans top-of-page regions; uses CLAHE, denoise, adaptive threshold, morphology, and rotations to improve decoding
- Treats the first `MAIN_PAGE_COUNT` pages as main; groups remaining pages into supplementary sets of size `SUPPL_SET_SIZE`
- Writes results to `<folder>.csv` and records the CSV name in `latest_report.txt`

### Key Settings (test.py)
- `PDF_FOLDER`: default search path for PDFs
- `MAIN_PAGE_COUNT`: expected main pages
- `SUPPL_SET_SIZE`: pages per supplementary set

## Usage
```bash
python test.py
```
1) Enter the folder path containing PDFs (or press Enter for the default).
2) Already-recorded files in the CSV are skipped.
3) Review the generated CSV for `match`/`mismatch` and issue details.

## Output CSV Columns
- Base: s.no, filename, md5, total_pages, expected_barcode, decoded_barcode, status, issue
- Supplementary: `supp_expected_barcode_N`, `supp_decoded_barcode_N` per set

## Troubleshooting
- If barcodes are faint, ensure the top page region is present; preprocessing already boosts contrast and rotates
- `total_pages` of 0 with issue "Cannot open PDF" means the PDF could not be parsed; re-export it
- To rerun from scratch, delete the generated CSV and `latest_report.txt`
```