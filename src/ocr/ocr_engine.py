import os
import re
import shutil
import cv2
import pytesseract
import pymupdf as fitz
import numpy as np
from typing import List


def configure_tesseract_path():
    """Find and set Tesseract executable path dynamically."""
    tesseract_in_path = shutil.which("tesseract")
    if tesseract_in_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_in_path
        return

    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return


configure_tesseract_path()


def _ocr_image(gray: np.ndarray, psm: int) -> str:
    """Run Tesseract OCR with a specific PSM mode and return text."""
    try:
        return pytesseract.image_to_string(gray, config=f"--psm {psm} -l eng")
    except Exception as e:
        return f"[OCR Error: {str(e)}]"


def extract_text(processed_image: np.ndarray, gray_image: np.ndarray = None) -> str:
    """
    Extract text using Tesseract OCR.

    Tries PSM 4, 6, and 3 on both CLAHE-enhanced gray AND binary threshold images.
    Picks the result with the highest combined word + number score.
    PSM 4 on raw gray is typically best for Indian invoices with summary tables.
    """
    def to_gray(img):
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    images_to_try = {}
    if gray_image is not None:
        images_to_try["gray"] = to_gray(gray_image)
    images_to_try["binary"] = to_gray(processed_image)

    candidates = {}
    for img_name, img in images_to_try.items():
        for psm in [4, 6, 3]:
            key = f"{img_name}_psm{psm}"
            t = _ocr_image(img, psm)
            if not t.startswith("[OCR Error"):
                candidates[key] = t

    best_text = ""
    best_score = -1
    for key, t in candidates.items():
        alpha_words = len(re.findall(r"[A-Za-z]{3,}", t))
        digit_seqs = len(re.findall(r"\d{3,}", t))
        score = alpha_words + digit_seqs * 2
        if score > best_score:
            best_score = score
            best_text = t

    return best_text


def extract_text_from_pdf_stream(pdf_bytes: bytes) -> str:
    """
    Extract embedded digital text from a vector PDF using PyMuPDF.
    Returns empty string if the PDF is scanned / raster-only.
    """
    full_text = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            t = page.get_text()
            if t.strip():
                full_text.append(t)
        doc.close()
    except Exception:
        pass
    return "\n--- Page Break ---\n".join(full_text)