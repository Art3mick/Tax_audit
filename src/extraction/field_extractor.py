import re
from typing import Dict, Any, List, Optional


def parse_number(text_val: Optional[str]) -> Optional[float]:
    """
    Normalizes numeric strings by removing currency symbols, commas, spaces.
    Handles common OCR noise like 'O' -> '0'.
    """
    if not text_val:
        return None
    cleaned = str(text_val).strip()
    # Remove currency symbols and formatting
    cleaned = cleaned.replace("₹", "").replace("Rs.", "").replace("Rs", "").replace(",", "").replace(" ", "")
    # Replace OCR noise: capital O that should be 0 (only if surrounded by digits)
    cleaned = re.sub(r"(?<!\w)O(?!\w)", "0", cleaned)
    # Keep only digits and a single decimal point
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    # Remove duplicate dots
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = parts[0] + "." + "".join(parts[1:])
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(date_str: Optional[str]) -> Optional[str]:
    """
    Normalizes dates into ISO format (YYYY-MM-DD).
    Supports YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD, DD-MMM-YYYY (29 Mar 2026, 05-Mar-2020), DD-MM-YYYY, DD/MM/YYYY, etc.
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # 1. YYYY-MM-DD or YYYY/MM/DD or YYYY.MM.DD
    match_ymd = re.search(r"(\d{4})[\s\-/\.](\d{1,2})[\s\-/\.](\d{1,2})", date_str)
    if match_ymd:
        year, month, day = match_ymd.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    # 2. DD-MMM-YYYY / DD MMM YYYY / DD.MMM.YYYY (e.g., 29 Mar 2026, 05-Mar-2020, 29 March 2026)
    match_mmm = re.search(r"(\d{1,2})[\s\-/\.]([A-Za-z]{3,9})[\s\-/\.](\d{2,4})", date_str)
    if match_mmm:
        day, month_str, year = match_mmm.groups()
        months = {
            "jan": "01", "january": "01",
            "feb": "02", "february": "02",
            "mar": "03", "march": "03",
            "apr": "04", "april": "04",
            "may": "05",
            "jun": "06", "june": "06",
            "jul": "07", "july": "07",
            "aug": "08", "august": "08",
            "sep": "09", "september": "09",
            "oct": "10", "october": "10",
            "nov": "11", "november": "11",
            "dec": "12", "december": "12"
        }
        m_num = months.get(month_str.lower(), months.get(month_str.lower()[:3]))
        if m_num:
            if len(year) == 2:
                year = "20" + year
            return f"{year}-{m_num}-{int(day):02d}"

    # 3. DD-MM-YYYY or DD/MM/YYYY or DD.MM.YYYY
    match_dmy = re.search(r"(\d{1,2})[\s\-/\.](\d{1,2})[\s\-/\.](\d{2,4})", date_str)
    if match_dmy:
        day, month, year = match_dmy.groups()
        if len(year) == 2:
            year = "20" + year
        return f"{year}-{int(month):02d}-{int(day):02d}"

    return date_str


def clean_gstin_ocr(raw: str) -> str:
    """
    Fixes common OCR substitutions in GSTINs.
    - Removes internal non-alphanumeric chars (dots, spaces, hyphens).
    - Takes exact 15-character GSTIN block (removes attached labels like PAN).
    - Positions 0-1 must be digits (state code): replace 'O' with '0', 'I'/'L' with '1'
    """
    cleaned = re.sub(r"[^A-Z0-9]", "", raw.upper().strip())
    cleaned = cleaned[:15]
    corrected = list(cleaned)
    for i in range(min(2, len(corrected))):
        corrected[i] = corrected[i].replace("O", "0").replace("I", "1").replace("L", "1")
    return "".join(corrected)


def extract_gstins(text: str) -> List[str]:
    """
    Finds GSTIN candidates from text.
    Includes OCR-error-tolerant matching (allows internal spaces/dots/hyphens).
    """
    candidates_raw = re.findall(r"\b[\dOo]{1,2}[\s\.\-]?[A-Z0-9\s\.\-]{12,16}\b", text.upper())
    cleaned_candidates = []
    for c in candidates_raw:
        cg = clean_gstin_ocr(c)
        if len(cg) == 15:
            cleaned_candidates.append(cg)

    simple_candidates = re.findall(r"\b[A-Z0-9]{15}\b", text.upper())
    for c in simple_candidates:
        cg = clean_gstin_ocr(c)
        if len(cg) == 15:
            cleaned_candidates.append(cg)

    return list(dict.fromkeys(cleaned_candidates))


def extract_amount_after_label(text: str, label_pattern: str) -> Optional[float]:
    """
    Extracts a monetary amount that appears on the SAME LINE as a given label.
    Works for both labeled (colon/equals) and space-separated layout (table rows).
    """
    match = re.search(
        label_pattern + r"[\s:₹\-]*([\d,]+\.?\d*)\s*$",
        text, re.IGNORECASE | re.MULTILINE
    )
    if match:
        return parse_number(match.group(1))
    return None


def extract_line_items(text: str) -> List[Dict[str, Any]]:
    """
    Extracts tabular line items (description, HSN/SAC, qty, rate, taxable, tax%, total).
    """
    items = []
    lines = text.split("\n")

    # Full line-item pattern: sr_no, description, HSN, qty, [unit], rate, taxable, tax%, tax_amt, total
    line_pattern = re.compile(
        r"^\s*(\d{1,2})\s+\|?\s*(.*?)\s+(\d{4,8})\s+"
        r"(\d+(?:[\.,]\d+)?)\s*(?:PCS|NOS|KG|LTR|MTR|UNIT|BAG|BOX|SET|PC|PIECE)?\s+"
        r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s*"
        r"(?:([\d.]+)\s*%?)?\s*"
        r"(?:([\d,]+(?:\.\d+)?)\s*)?"
        r"([\d,]+(?:\.\d+)?)\s*\|?\s*$",
        re.IGNORECASE
    )

    for line in lines:
        match = line_pattern.search(line)
        if match:
            sr_no, desc, hsn, qty, rate, taxable, tax_pct, tax_amt, total = match.groups()
            items.append({
                "sr_no": int(sr_no),
                "description": desc.strip().strip("|").strip(),
                "hsn_sac": hsn.strip(),
                "quantity": parse_number(qty),
                "unit": "PCS",
                "rate": parse_number(rate),
                "taxable_amount": parse_number(taxable),
                "tax_rate": parse_number(tax_pct) if tax_pct else None,
                "tax_amount": parse_number(tax_amt) if tax_amt else None,
                "total_amount": parse_number(total)
            })

    # Line item pattern 2 (Description + HSN + Qty + Unit + Rate + Tax + Total without required sr_no)
    if not items:
        line_pattern_2 = re.compile(
            r"^\s*(?:(\d{1,2})\s+)?([A-Za-z0-9 \-_&()]+?)\s+(\d{4,8})\s+"
            r"(\d+(?:[\.,]\d+)?)\s*([A-Za-z]{1,6})\s+"
            r"([\d,]+(?:\.\d+)?)\s+"
            r"([\d,]+(?:\.\d+)?)\s*"
            r"(?:\((\d+(?:\.\d+)?)\%\))?\s*"
            r"([\d,]+(?:\.\d+)?)\s*$",
            re.IGNORECASE
        )
        for idx, line in enumerate(lines, start=1):
            m2 = line_pattern_2.search(line)
            if m2:
                sr, desc, hsn, qty, unit, rate, tax_amt, tax_pct, total = m2.groups()
                items.append({
                    "sr_no": int(sr) if sr else idx,
                    "description": desc.strip(),
                    "hsn_sac": hsn.strip(),
                    "quantity": parse_number(qty),
                    "unit": unit.upper(),
                    "rate": parse_number(rate),
                    "taxable_amount": round((parse_number(qty) or 1.0) * (parse_number(rate) or 0.0), 2) if parse_number(rate) else None,
                    "tax_rate": parse_number(tax_pct) if tax_pct else None,
                    "tax_amount": parse_number(tax_amt) if tax_amt else None,
                    "total_amount": parse_number(total)
                })

    # Simpler fallback: sr_no + HSN + at least two numbers
    if not items:
        fallback_pattern = re.compile(
            r"(\d{1,2})\s+\|?\s*([A-Za-z0-9 \-_&()]+?)\s+(\d{4,8})\s+(\d+(?:[\.,]\d+)?)"
        )
        for line in lines:
            f_match = fallback_pattern.search(line)
            if f_match:
                sr, desc, hsn, qty = f_match.groups()
                items.append({
                    "sr_no": int(sr),
                    "description": desc.strip().strip("|").strip(),
                    "hsn_sac": hsn,
                    "quantity": parse_number(qty),
                    "unit": "PCS",
                    "rate": None,
                    "taxable_amount": None,
                    "tax_rate": None,
                    "tax_amount": None,
                    "total_amount": None
                })

    return items


def extract_fields(text: str) -> Dict[str, Any]:
    """
    Extracts structured financial information from OCR raw text.
    Implements the Generic Invoice Schema with Common and Optional fields.
    """
    fields: Dict[str, Any] = {
        # Common Fields
        "invoice_number": None,
        "invoice_date": None,
        "supplier_name": None,
        "supplier_address": None,
        "supplier_gstin": None,
        "customer_name": None,
        "customer_address": None,
        "customer_gstin": None,
        "items": [],
        "quantity": None,
        "unit_price": None,
        "taxable_amount": None,
        "gst_rate": None,
        "cgst": None,
        "sgst": None,
        "igst": None,
        "total_tax": None,
        "total_amount": None,
        "currency": "INR",
        "raw_text": text,

        # Optional Fields
        "proforma_number": None,
        "proforma_date": None,
        "vehicle_number": None,
        "transporter_name": None,
        "transport_details": None,
        "reverse_charge": "Not detected",
        "purchase_order_number": None,
        "eway_bill_number": None,
        "delivery_address": None,
        "payment_terms": None,
        "bank_details": {
            "bank_name": None,
            "branch": None,
            "account_number": None,
            "ifsc": None
        },
        "due_date": None,
        "place_of_supply": None,
        "amount_in_words": None,
        "challan_number": None,
        "lr_number": None,
    }

    if not text or not text.strip():
        return fields

    # ----------------------------------------------------------------
    # 1. GSTIN Extraction (OCR-noise tolerant & Section-aware)
    # ----------------------------------------------------------------
    all_gst_matches = re.findall(
        r"(?:GSTIN|GST)\s*[:\-]?\s*\b([0-9A-Z\.\-]{10,15})\b",
        text, re.I
    )
    cleaned_labeled = []
    for g in all_gst_matches:
        cg = clean_gstin_ocr(g)
        if len(cg) >= 10:
            cleaned_labeled.append(cg)

    gstin_list = extract_gstins(text)
    combined_gstins = list(dict.fromkeys(cleaned_labeled + gstin_list))

    if len(combined_gstins) >= 1:
        fields["supplier_gstin"] = combined_gstins[0]
    if len(combined_gstins) >= 2:
        fields["customer_gstin"] = combined_gstins[1]

    # Explicit Customer GSTIN context
    cust_gst_match = re.search(
        r"(?:BILL\s*TO|BUYER|CUSTOMER|SHIP\s*TO)[\s\S]*?(?:GSTIN|GST)\s*[:\-]?\s*\b([0-9A-Z\.\-]{10,15})\b",
        text, re.I
    )
    if cust_gst_match:
        cg = clean_gstin_ocr(cust_gst_match.group(1))
        if len(cg) >= 10:
            fields["customer_gstin"] = cg

    # ----------------------------------------------------------------
    # 2. Invoice / Proforma / Challan Numbers
    # ----------------------------------------------------------------
    inv_matches = re.findall(
        r"(?:Invoice|Bill|Inv)\s*(?:No|Num|Number|#|\.)\s*[:\-]?\s*([A-Za-z0-9/\-]+)",
        text, re.I
    )
    for match_val in inv_matches:
        clean_val = match_val.strip().strip(".")
        if clean_val.upper() not in ["ORIGINAL", "DUPLICATE", "TRIPLICATE", "RECIPIENT", "SUPPLIER", "TAX", "INVOICE", "DATE"]:
            fields["invoice_number"] = clean_val
            break

    if not fields["invoice_number"]:
        fallback_inv = re.search(
            r"(?:Tax\s*Invoice|Ref)\s*(?:No|Num|Number|\.)\s*[:\-]?\s*([A-Za-z0-9/\-]+)",
            text, re.I
        )
        if fallback_inv:
            val = fallback_inv.group(1).strip().strip(".")
            if val.upper() not in ["ORIGINAL", "DUPLICATE", "TRIPLICATE", "RECIPIENT", "SUPPLIER", "TAX", "INVOICE", "DATE"]:
                fields["invoice_number"] = val

    proforma_match = re.search(
        r"Proforma\s*(?:No|Num|Number|\.)\s*[:\-]?\s*([A-Za-z0-9/\-]+)",
        text, re.I
    )
    if proforma_match:
        fields["proforma_number"] = proforma_match.group(1).strip()
        if not fields["invoice_number"]:
            fields["invoice_number"] = fields["proforma_number"]

    challan_match = re.search(
        r"Challan\s*(?:No|Num|Number|\.)\s*[:\-]?\s*([A-Za-z0-9/\-]+)",
        text, re.I
    )
    if challan_match:
        fields["challan_number"] = challan_match.group(1).strip()

    lr_match = re.search(r"L\.?R\.?\s*No\.?\s*[:\-]?\s*(\d+)", text, re.I)
    if lr_match:
        fields["lr_number"] = lr_match.group(1).strip()

    # ----------------------------------------------------------------
    # 3. Dates
    # ----------------------------------------------------------------
    inv_date_match = re.search(
        r"(?:Invoice|Bill|Document)\s*Date\s*[:\-]?\s*(\d{1,2}[\s\-/\.](?:[A-Za-z]{3,9}|\d{1,2})[\s\-/\.]\d{2,4})",
        text, re.I
    )
    if inv_date_match:
        fields["invoice_date"] = parse_date(inv_date_match.group(1))

    proforma_date_match = re.search(
        r"Proforma\s*Date\s*[:\-]?\s*(\d{1,2}[\s\-/\.](?:[A-Za-z]{3,9}|\d{1,2})[\s\-/\.]\d{2,4})",
        text, re.I
    )
    if proforma_date_match:
        fields["proforma_date"] = parse_date(proforma_date_match.group(1))
        if not fields["invoice_date"]:
            fields["invoice_date"] = fields["proforma_date"]

    if not fields["invoice_date"]:
        challan_date = re.search(
            r"Challan\s*Date\s*[:\-]?\s*(\d{1,2}[\s\-/\.](?:[A-Za-z]{3,9}|\d{1,2})[\s\-/\.]\d{2,4})",
            text, re.I
        )
        if challan_date:
            fields["invoice_date"] = parse_date(challan_date.group(1))

    if not fields["invoice_date"]:
        any_date = re.search(r"\b(\d{1,2}[\s\-/\.](?:[A-Za-z]{3,9}|\d{1,2})[\s\-/\.]\d{2,4})\b", text)
        if any_date:
            fields["invoice_date"] = parse_date(any_date.group(1))

    # ----------------------------------------------------------------
    # 4. Supplier & Customer Names
    # ----------------------------------------------------------------
    text_lines = [line.strip() for line in text.split("\n") if line.strip()]
    if text_lines:
        for l in text_lines[:3]:
            if len(l) > 5 and not re.match(r"^[\W\d]+$", l):
                clean_l = re.sub(r"\b(?:TAX\s*INVOICE|INVOICE|ORIGINAL|DUPLICATE|TRIPLICATE|FOR\s*RECIPIENT|RECIPIENT)\b.*$", "", l, flags=re.I).strip().strip(".").strip()
                if clean_l:
                    fields["supplier_name"] = clean_l
                else:
                    fields["supplier_name"] = l.strip()
                break

    cust_match = re.search(r"(?:M/?[Ss]|BILL\s*TO|BUYER)\s*[:\-]?\s*([A-Za-z0-9\s&.,'()\-]+)", text, re.I)
    if cust_match:
        fields["customer_name"] = cust_match.group(1).split("\n")[0].strip()

    # ----------------------------------------------------------------
    # 5. Place of Supply
    # ----------------------------------------------------------------
    pos_match = re.search(r"(?:Place|Pl\.?)\s*of\s*Supply\s*[:\-]?\s*([A-Za-z0-9\s()]+)", text, re.I)
    if pos_match:
        fields["place_of_supply"] = pos_match.group(1).strip().split("\n")[0]

    # ----------------------------------------------------------------
    # 6. Financial Amounts — ROBUST multi-pattern extraction
    # ----------------------------------------------------------------
    # Taxable Amount
    taxable_patterns = [
        r"Taxable\s*(?:Amount|Value)\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
        r"Sub[\s\-]?[Tt]otal\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
    ]
    for pat in taxable_patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            fields["taxable_amount"] = parse_number(m.group(1))
            break

    # CGST Amount & Rate
    cgst_rate = None
    cgst_match = re.search(
        r"CGST\s*(?:@|\(?)\s*(\d{1,2}(?:\.\d+)?)\s*%?\)?\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
        text, re.IGNORECASE | re.MULTILINE
    )
    if cgst_match:
        cgst_rate = parse_number(cgst_match.group(1))
        fields["cgst"] = parse_number(cgst_match.group(2))
    else:
        cgst_plain = re.search(
            r"CGST\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
            text, re.IGNORECASE | re.MULTILINE
        )
        if cgst_plain:
            fields["cgst"] = parse_number(cgst_plain.group(1))

    # SGST Amount & Rate
    sgst_rate = None
    sgst_match = re.search(
        r"SGST\s*(?:@|\(?)\s*(\d{1,2}(?:\.\d+)?)\s*%?\)?\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
        text, re.IGNORECASE | re.MULTILINE
    )
    if sgst_match:
        sgst_rate = parse_number(sgst_match.group(1))
        fields["sgst"] = parse_number(sgst_match.group(2))
    else:
        sgst_plain = re.search(
            r"SGST\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
            text, re.IGNORECASE | re.MULTILINE
        )
        if sgst_plain:
            fields["sgst"] = parse_number(sgst_plain.group(1))

    # IGST Amount & Rate
    igst_rate = None
    igst_match = re.search(
        r"(?:Add\s*[:\-]\s*)?IGST\s*(?:@|\(?)\s*(\d{1,2}(?:\.\d+)?)\s*%?\)?\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
        text, re.IGNORECASE | re.MULTILINE
    )
    if igst_match:
        igst_rate = parse_number(igst_match.group(1))
        fields["igst"] = parse_number(igst_match.group(2))
    else:
        igst_plain = re.search(
            r"(?:Add\s*[:\-]\s*)?IGST\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
            text, re.IGNORECASE | re.MULTILINE
        )
        if igst_plain:
            fields["igst"] = parse_number(igst_plain.group(1))

    # Total Tax
    total_tax_match = re.search(
        r"Total\s*Tax\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
        text, re.IGNORECASE | re.MULTILINE
    )
    if total_tax_match:
        fields["total_tax"] = parse_number(total_tax_match.group(1))

    # Derive total_tax if not found
    if fields["total_tax"] is None:
        if fields["igst"] is not None:
            fields["total_tax"] = fields["igst"]
        elif fields["cgst"] is not None and fields["sgst"] is not None:
            fields["total_tax"] = round(fields["cgst"] + fields["sgst"], 2)

    # Sanity check for CGST/SGST OCR misreads (e.g., 254.77 instead of 54.77 when total_tax is 109.53)
    if fields["total_tax"] is not None:
        if fields["cgst"] is not None and fields["cgst"] > fields["total_tax"]:
            if fields["sgst"] is not None and fields["sgst"] <= fields["total_tax"]:
                fields["cgst"] = round(fields["total_tax"] - fields["sgst"], 2)
            else:
                fields["cgst"] = round(fields["total_tax"] / 2.0, 2)

        if fields["sgst"] is not None and fields["sgst"] > fields["total_tax"]:
            if fields["cgst"] is not None and fields["cgst"] <= fields["total_tax"]:
                fields["sgst"] = round(fields["total_tax"] - fields["cgst"], 2)
            else:
                fields["sgst"] = round(fields["total_tax"] / 2.0, 2)

    # Grand Total
    total_patterns = [
        r"Total\s*Amount\s*After\s*Tax\s*[:\-]?\s*₹?\s*\'?\s*([\d,]+\.?\d*)",
        r"Grand\s*Total\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
        r"Amount\s*Payable\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
        r"Total\s*Amount\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
        r"NET\s*(?:TOTAL|AMOUNT)\s*[:\-]?\s*₹?\s*([\d,]+\.?\d*)",
    ]
    for pat in total_patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            val = parse_number(m.group(1))
            if val is not None and val > 0:
                fields["total_amount"] = val
                break

    # GST Rate Determination (safe & precise)
    if cgst_rate is not None and sgst_rate is not None:
        fields["gst_rate"] = round(cgst_rate + sgst_rate, 2)
    elif igst_rate is not None:
        fields["gst_rate"] = igst_rate
    else:
        gst_label_match = re.search(
            r"(?:GST|Tax\s*Rate)\s*@?\s*(\d{1,2}(?:\.\d+)?)\s*%",
            text, re.IGNORECASE
        )
        if gst_label_match:
            fields["gst_rate"] = parse_number(gst_label_match.group(1))

    # ----------------------------------------------------------------
    # 7. Amount in Words
    # ----------------------------------------------------------------
    words_match = re.search(
        r"((?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|"
        r"THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY|"
        r"THIRTY|FORTY|FIFTY|SIXTY|SEVENTY|EIGHTY|NINETY|HUNDRED|THOUSAND|LAKH|"
        r"CRORE|RUPEE)[A-Z\s]+ONLY)",
        text.upper()
    )
    if words_match:
        fields["amount_in_words"] = words_match.group(1).strip()

    # ----------------------------------------------------------------
    # 8. Optional Transport / Logistics fields
    # ----------------------------------------------------------------
    vehicle_match = re.search(
        r"Vehicle\s*(?:Number|No)\s*[:\-]?\s*([A-Z]{2}\s*\d{1,2}\s*[A-Z]{1,3}\s*\d{4})",
        text, re.I
    )
    if vehicle_match:
        fields["vehicle_number"] = re.sub(r"\s+", "", vehicle_match.group(1).upper())

    transporter_match = re.search(r"Transport(?:er)?\s*[:\-]?\s*([A-Za-z0-9\s]+)", text, re.I)
    if transporter_match:
        val = transporter_match.group(1).strip().split("\n")[0].strip()
        if len(val) > 2:
            fields["transporter_name"] = val

    reverse_charge_match = re.search(
        r"Reverse\s*Charge\s*[:\-=]?\s*(Yes|No|N\.?A\.?)",
        text, re.I
    )
    if reverse_charge_match:
        fields["reverse_charge"] = reverse_charge_match.group(1).capitalize()

    # ----------------------------------------------------------------
    # 9. Bank Details
    # ----------------------------------------------------------------
    bank_name_m = re.search(r"Bank\s*Name\s*[:\-]?\s*([A-Za-z0-9\s]+)", text, re.I)
    if bank_name_m:
        fields["bank_details"]["bank_name"] = bank_name_m.group(1).strip().split("\n")[0]

    branch_m = re.search(r"Branch\s*(?:Name)?\s*[:\-]?\s*([A-Za-z0-9\s]+)", text, re.I)
    if branch_m:
        fields["bank_details"]["branch"] = branch_m.group(1).strip().split("\n")[0]

    acc_m = re.search(r"(?:Account|A/?C)\s*(?:Number|No)\.?\s*[:\-]?\s*(\d{9,18})", text, re.I)
    if acc_m:
        fields["bank_details"]["account_number"] = acc_m.group(1)

    ifsc_m = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text)
    if ifsc_m:
        fields["bank_details"]["ifsc"] = ifsc_m.group(1)

    # ----------------------------------------------------------------
    # 10. Line Items Table
    # ----------------------------------------------------------------
    fields["items"] = extract_line_items(text)
    if fields["items"]:
        qtys = [item["quantity"] for item in fields["items"] if item.get("quantity")]
        if qtys:
            fields["quantity"] = round(sum(qtys), 2)

        # Derive taxable_amount from line items if not found in summary
        if fields["taxable_amount"] is None:
            item_taxables = [
                item["taxable_amount"] for item in fields["items"]
                if item.get("taxable_amount")
            ]
            if item_taxables:
                fields["taxable_amount"] = round(sum(item_taxables), 2)

        # Derive GST rate from items if not found
        if fields["gst_rate"] is None:
            item_rates = [
                item["tax_rate"] for item in fields["items"]
                if item.get("tax_rate")
            ]
            if item_rates:
                fields["gst_rate"] = item_rates[0]  # Use first item's rate

    # Final fallback for GST rate: calculate from total_tax / taxable_amount
    if fields["gst_rate"] is None and fields.get("taxable_amount") and fields.get("total_tax") and fields["taxable_amount"] > 0:
        fields["gst_rate"] = round((fields["total_tax"] / fields["taxable_amount"]) * 100, 2)

    return fields