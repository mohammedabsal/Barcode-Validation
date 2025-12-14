import os
import sys
import hashlib
import datetime
import fitz
from PIL import Image, ImageEnhance, ImageFilter
import zxingcpp
import pandas as pd
import csv
from collections import Counter

import cv2
import numpy as np

# ---------- CONFIG ----------
PDF_FOLDER = "./"
MAIN_PAGE_COUNT = 34
SUPPL_SET_SIZE = 4
STATE_FILE = "latest_report.txt"
BASE_HEADER = [
    "s.no",
    "filename",
    "md5",
    "total_pages",
    "expected_barcode",
    "decoded_barcode",
]
# ----------------------------


def md5sum(file_path):
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def get_report_file():
    folder_base = os.path.basename(os.path.abspath(PDF_FOLDER)) or "pdf"
    csv_name = f"{folder_base}.csv"

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(csv_name)

    if not os.path.exists(csv_name):
        header = BASE_HEADER + ["status", "issue"]
        with open(csv_name, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

    return csv_name


def read_csv_all(csv_path):
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def write_csv_all(csv_path, rows):
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def ensure_header_has_supp_sets(csv_path, num_supp_sets):
    rows = read_csv_all(csv_path)

    if not rows:
        header = BASE_HEADER[:]
        for i in range(1, num_supp_sets + 1):
            header.append(f"supp_expected_barcode_{i}")
            header.append(f"supp_decoded_barcode_{i}")
        header.extend(["status", "issue"])
        write_csv_all(csv_path, [header])
        return header

    header = rows[0]
    existing_supp = 0
    for part in header:
        if part.startswith("supp_expected_barcode_"):
            try:
                idx = int(part.split("_")[-1])
                existing_supp = max(existing_supp, idx)
            except:
                pass

    if existing_supp >= num_supp_sets:
        return header

    new_header = BASE_HEADER[:]
    for i in range(1, num_supp_sets + 1):
        new_header.append(f"supp_expected_barcode_{i}")
        new_header.append(f"supp_decoded_barcode_{i}")

    new_header.extend(["status", "issue"])

    new_rows = [new_header]
    for old in rows[1:]:
        old = list(old)
        if len(old) < len(new_header):
            old.extend(["-"] * (len(new_header) - len(old)))
        else:
            old = old[:len(new_header)]
        new_rows.append(old)

    write_csv_all(csv_path, new_rows)
    return new_header


# -------------------------------------------------------
# 🔥 OPENCV PREPROCESSING (Fixes faint barcodes)
# -------------------------------------------------------
def preprocess_for_barcode(pil_img):
    img = np.array(pil_img)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # 1. CLAHE (adaptive contrast boost)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    cl = clahe.apply(gray)

    # 2. Bilateral filter (removes noise but keeps barcode edges)
    denoised = cv2.bilateralFilter(cl, 9, 75, 75)

    # 3. Adaptive threshold (fixes light print barcodes)
    thresh = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        35, 10
    )

    # 4. Morph close to thicken faint bars
    kernel = np.ones((3, 3), np.uint8)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    return Image.fromarray(closed)


# -------------------------------------------------------
# 🔥 Improved Decode Function (ZXing + OpenCV)
# -------------------------------------------------------
def enhanced_decode(pil_img):
    # Try direct first
    try:
        res = zxingcpp.read_barcode(pil_img)
        if res and res.text:
            return res.text.strip().upper()
    except:
        pass

    # Try OpenCV processed
    processed = preprocess_for_barcode(pil_img)
    try:
        res = zxingcpp.read_barcode(processed)
        if res and res.text:
            return res.text.strip().upper()
    except:
        pass

    # Try rotations
    for angle in [90, 180, 270]:
        try:
            rot = processed.rotate(angle, expand=True)
            res = zxingcpp.read_barcode(rot)
            if res and res.text:
                return res.text.strip().upper()
        except:
            pass

    return None


# -------------------------------------------------------
# 📌 MAIN VALIDATION
# -------------------------------------------------------
def validate(pdf_path, csv_path):
    filename = os.path.basename(pdf_path)
    expected = os.path.splitext(filename)[0].upper()

    try:
        if os.path.exists(csv_path):
            with open(csv_path, "r") as f:
                s_no = max(0, sum(1 for _ in f) - 1) + 1
        else:
            s_no = 1
    except:
        s_no = 1

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        # record total_pages as 0 when PDF cannot be opened
        save_result_row(csv_path, [s_no, filename, "", 0, expected, "", "mismatch", "Cannot open PDF"])
        return

    total_pages = len(doc)
    print(f"Pages: {total_pages}")

    page_infos = []

    for page_num, page in enumerate(doc, 1):
        pix = page.get_pixmap(dpi=900)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        w, h = img.size

        crop_boxes = [
            (0, 0, w, int(h * 0.12)),   # New top full-width region
            (int(w * 0.6), 0, w, int(h * 0.20)),
            (int(w * 0.5), 0, w, int(h * 0.30)),
            (int(w * 0.45), 0, w, int(h * 0.40)),
        ]

        code = None

        for cb in crop_boxes:
            cropped = img.crop(cb)
            code = enhanced_decode(cropped)
            if code:
                break

        if not code:
            fallback = img.crop((0, 0, w, int(h * 0.15)))
            code = enhanced_decode(fallback)

        page_infos.append({"page_num": page_num, "code": code})

    # MAIN logic unchanged
    main_missing = []
    main_mismatch = []

    for info in page_infos:
        if info["page_num"] <= MAIN_PAGE_COUNT:
            c = info["code"]
            if not c:
                main_missing.append(info["page_num"])
            elif c != expected:
                main_mismatch.append(info["page_num"])

    supp_start = MAIN_PAGE_COUNT + 1
    supp_pages = [p for p in page_infos if p["page_num"] >= supp_start]

    num_supp_sets = (max(0, total_pages - MAIN_PAGE_COUNT) + SUPPL_SET_SIZE - 1) // SUPPL_SET_SIZE

    supp_rows = []
    for i in range(num_supp_sets):
        group_start = MAIN_PAGE_COUNT + 1 + (i * SUPPL_SET_SIZE)
        group = [g for g in supp_pages if group_start <= g["page_num"] < group_start + SUPPL_SET_SIZE]
        codes = [g["code"] or "" for g in group]
        unique_values = sorted({c for c in codes if c})
        if not unique_values:
            supp_rows.append(("-", "-"))
            continue
        supp_expected = Counter(unique_values).most_common(1)[0][0]
        supp_decoded = ",".join(unique_values)
        supp_rows.append((supp_expected, supp_decoded))

    if num_supp_sets == 0:
        supp_rows = [("-", "-")]

    details = []
    if main_mismatch:
        details.append(f"Main mismatches: {main_mismatch}")
    if main_missing:
        details.append(f"Main missing: {main_missing}")

    supp_issues = []
    if num_supp_sets > 0:
        for idx, (exp_v, dec_v) in enumerate(supp_rows, 1):
            if dec_v == "-":
                supp_issues.append({"set": idx, "issue": "All missing"})
            elif exp_v not in dec_v.split(","):
                supp_issues.append({"set": idx, "decoded": dec_v})

    if supp_issues:
        details.append(f"Supp issues: {supp_issues}")

    detail_text = "; ".join(details) if details else "-"

    main_codes = [i["code"] for i in page_infos if i["page_num"] <= MAIN_PAGE_COUNT and i["code"]]
    decoded_barcode = Counter(main_codes).most_common(1)[0][0] if main_codes else "-"

    overall_status = "match" if not (main_missing or main_mismatch or supp_issues) else "mismatch"

    ensure_header_has_supp_sets(csv_path, max(1, num_supp_sets))

    row = [
        s_no,
        filename,
        md5sum(pdf_path),
        total_pages,
        expected,
        decoded_barcode,
    ]

    for exp_val, dec_val in supp_rows:
        row.append(exp_val)
        row.append(dec_val)

    row.extend([overall_status, detail_text])
    save_result_row(csv_path, row)

    print(f"Completed: {filename} | {overall_status} | {detail_text}")


def save_result_row(csv_path, row):
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(row)


def main():
    global PDF_FOLDER

    while True:
        inp = input(f"Folder path containing PDFs [{PDF_FOLDER}]: ").strip()
        if inp:
            PDF_FOLDER = inp

        if not os.path.isdir(PDF_FOLDER):
            print("Invalid folder")
            retry = input("Press Enter to retry or 'exit': ").strip()
            if retry.lower() == "exit":
                break
            if os.path.isdir(retry):
                PDF_FOLDER = retry
                continue
            continue

        csv_path = get_report_file()

        try:
            existing = pd.read_csv(csv_path)["filename"].fillna("").tolist()
        except:
            existing = []

        pdfs = [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")]

        print(f"\nReport: {csv_path}")
        print(f"Already validated: {len(existing)}")
        print(f"Total PDFs: {len(pdfs)}\n")

        for idx, pdf in enumerate(pdfs, start=1):
            if pdf in existing:
                print(f"Skipping ({idx}/{len(pdfs)}): {pdf} (already validated)")
                continue

            print(f"\nProcessing ({idx}/{len(pdfs)}): {pdf}")
            validate(os.path.join(PDF_FOLDER, pdf), csv_path)

        print("\nAll PDFs processed!")

        ch = input("\nPress Enter to exit or A to process another: ").strip()
        if not ch:
            break
        if ch.upper() == "A":
            continue
        PDF_FOLDER = ch


if __name__ == "__main__":
    main()
