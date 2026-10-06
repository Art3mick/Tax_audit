import cv2
import numpy as np
import pymupdf as fitz
from typing import List, Tuple, Dict, Any


def deskew_image(image: np.ndarray) -> np.ndarray:
    """
    Detect image rotation angle and deskew it to straighten text lines.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    # Invert image for contour detection
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    
    # Find all white pixels
    coords = np.column_stack(np.where(thresh > 0))
    if coords.shape[0] < 50:
        return image
        
    angle = cv2.minAreaRect(coords)[-1]
    
    if angle < -45:
        angle = -(90 + angle)
    elif angle > 45:
        angle = 90 - angle
    else:
        angle = -angle
        
    # Ignore negligible angles
    if abs(angle) < 0.5 or abs(angle) > 30:
        return image

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )
    return rotated


def preprocess_image(image_bytes: bytes) -> Tuple[np.ndarray, np.ndarray]:
    """
    Preprocess raw image bytes for OCR:
    - Resizing for readability
    - Deskewing
    - CLAHE contrast enhancement
    - Noise reduction and Adaptive thresholding
    Returns (original_bgr, processed_gray).
    """
    image_array = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError("Unable to decode image bytes.")

    # 1. Deskew
    image = deskew_image(image)

    # 2. Resize if small
    height, width = image.shape[:2]
    if width < 1200:
        scale = 1200 / width
        image = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

    # 3. Grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 4. CLAHE Contrast Enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 5. Denoise with Gaussian Blur
    denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)

    # 6. Clean Otsu Binarization (avoids speckle/dithering noise)
    _, processed = cv2.threshold(
        denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    return image, processed, enhanced  # (bgr_original, binary_thresh, clahe_gray)


def extract_pages_from_pdf(pdf_bytes: bytes) -> List[np.ndarray]:
    """
    Renders each PDF page as a BGR OpenCV image at 300 DPI.
    """
    pages_bgr = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        zoom = 300 / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
        img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)
        pages_bgr.append(img_bgr)
        
    doc.close()
    return pages_bgr


def process_document(file_bytes: bytes, file_type: str) -> List[Dict[str, Any]]:
    """
    Processes any supported document (Image or PDF) and returns page records.
    Each record contains:
    - page_num (1-indexed)
    - original
    - processed
    """
    results = []
    file_type_lower = file_type.lower()
    
    if "pdf" in file_type_lower:
        pdf_pages = extract_pages_from_pdf(file_bytes)
        for idx, page_bgr in enumerate(pdf_pages, start=1):
            is_success, buffer = cv2.imencode(".png", page_bgr)
            if is_success:
                orig, proc, gray = preprocess_image(buffer.tobytes())
            else:
                gray = cv2.cvtColor(page_bgr, cv2.COLOR_BGR2GRAY)
                orig, proc = page_bgr, gray
            results.append({
                "page_num": idx,
                "original": orig,
                "processed": proc,
                "gray": gray
            })
    else:
        orig, proc, gray = preprocess_image(file_bytes)
        results.append({
            "page_num": 1,
            "original": orig,
            "processed": proc,
            "gray": gray
        })
        
    return results