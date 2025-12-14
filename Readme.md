```markdown
# PDF Barcode Validation Toolkit
Lightweight utilities for validating PDF batches that contain main and supplementary barcode pages.

## Requirements
- Python 3.10+
- Packages: pymupdf (fitz), pillow, zxing-cpp, opencv-python, pandas, numpy
- Works on Windows/macOS/Linux with standard PDFs (no external binaries needed)

Install deps:
```bash
pip install pymupdf pillow zxing-cpp opencv-python pandas numpy
```

## How It Works
- Reads all PDFs in a target folder (default: current directory).
- Derives the expected barcode from the PDF filename.
- Scans page top regions; uses CLAHE, denoise, adaptive threshold, morphology, and rotations to improve decoding.
- First `MAIN_PAGE_COUNT` pages are main; remaining pages are grouped into supplementary sets of size `SUPPL_SET_SIZE`.
- Results go to `<folder>.csv` and the CSV name is recorded in `latest_report.txt`.

Key settings in test.py:
- `PDF_FOLDER`: default search path.
- `MAIN_PAGE_COUNT`: number of main pages expected.
- `SUPPL_SET_SIZE`: size of each supplementary group.

## Usage
```bash
python test.py
```
1) Enter the folder path containing PDFs (or press Enter for default).
2) Already-recorded files in the CSV are skipped.
3) Review the generated CSV for `match`/`mismatch` and issue details.

## Output CSV Columns
- Base: s.no, filename, md5, total_pages, expected_barcode, decoded_barcode, status, issue
- Supplementary: pairs of `supp_expected_barcode_N` and `supp_decoded_barcode_N` per set.

## Troubleshooting
- If barcodes are faint, ensure the top page region is present; preprocessing already boosts contrast and rotates.
- `total_pages` of 0 with issue "Cannot open PDF" means the PDF could not be parsed; re-export it.
- To re-run from scratch, delete the generated CSV and `latest_report.txt`.
```