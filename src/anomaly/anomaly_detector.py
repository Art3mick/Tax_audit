from typing import List, Dict, Any


def detect_anomalies(
    extracted_fields: Dict[str, Any],
    tax_validation: Dict[str, Any],
    high_value_threshold: float = 100000.0
) -> List[Dict[str, Any]]:
    """
    Detects missing mandatory fields, invalid amounts, tax mismatches,
    and high-value invoice flags.
    Returns a list of structured anomaly objects.
    """
    anomalies: List[Dict[str, Any]] = []

    # 1. Missing Mandatory Audit Fields
    mandatory_fields = [
        ("invoice_number", "Invoice Number", "HIGH"),
        ("invoice_date", "Invoice Date", "HIGH"),
        ("supplier_gstin", "Supplier GSTIN", "HIGH"),
        ("taxable_amount", "Taxable Amount", "HIGH"),
        ("total_amount", "Grand Total Amount", "HIGH")
    ]

    for field_key, field_name, severity in mandatory_fields:
        val = extracted_fields.get(field_key)
        if val is None or (isinstance(val, str) and not val.strip()):
            anomalies.append({
                "field": field_key,
                "issue": f"Missing mandatory field: {field_name}",
                "severity": severity,
                "evidence": "Field absent or could not be detected from OCR text."
            })

    # 2. Invalid / Negative / Zero Amounts
    taxable = extracted_fields.get("taxable_amount")
    total = extracted_fields.get("total_amount")

    if taxable is not None and taxable <= 0:
        anomalies.append({
            "field": "taxable_amount",
            "issue": "Invalid Taxable Amount (Zero or Negative)",
            "severity": "HIGH",
            "evidence": f"Stated Taxable Amount is {taxable}."
        })

    if total is not None and total <= 0:
        anomalies.append({
            "field": "total_amount",
            "issue": "Invalid Grand Total Amount (Zero or Negative)",
            "severity": "HIGH",
            "evidence": f"Stated Grand Total Amount is {total}."
        })

    # 3. Taxable Amount Greater Than Total Amount
    if taxable is not None and total is not None:
        if taxable > total:
            anomalies.append({
                "field": "taxable_amount",
                "issue": "Taxable Amount exceeds Grand Total Amount",
                "severity": "HIGH",
                "evidence": f"Taxable Amount (₹{taxable}) > Grand Total (₹{total})."
            })

    # 4. Tax Validation & Regime Mismatches
    discrepancies = tax_validation.get("discrepancies", [])
    for disc in discrepancies:
        sev = "HIGH" if "Error" in disc or "Regime" in disc else "MEDIUM"
        anomalies.append({
            "field": "tax_validation",
            "issue": disc,
            "severity": sev,
            "evidence": f"Regime: {tax_validation.get('tax_regime')}"
        })

    # 5. Line Item Arithmetic Discrepancies
    items = extracted_fields.get("items", [])
    for item in items:
        qty = item.get("quantity")
        rate = item.get("rate")
        item_taxable = item.get("taxable_amount")
        
        if qty and rate and item_taxable:
            expected_taxable = round(qty * rate, 2)
            if abs(expected_taxable - item_taxable) > 1.0:
                anomalies.append({
                    "field": "items",
                    "issue": f"Line Item #{item.get('sr_no')} Math Mismatch",
                    "severity": "MEDIUM",
                    "evidence": f"Description: '{item.get('description')}'. Qty ({qty}) * Rate ({rate}) = {expected_taxable}, but stated Taxable is {item_taxable}."
                })

    # 6. High Value Purchase Threshold Alert
    if total is not None and total >= high_value_threshold:
        anomalies.append({
            "field": "total_amount",
            "issue": f"High-Value Transaction Alert (>= ₹{high_value_threshold:,.2f})",
            "severity": "LOW",
            "evidence": f"Invoice total is ₹{total:,.2f}. Mandatory CA verification recommended for ITC audit."
        })

    return anomalies
