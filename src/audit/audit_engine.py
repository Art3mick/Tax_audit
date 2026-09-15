from typing import Dict, Any, List
from src.tax.tax_engine import validate_tax, validate_gstin_format, calculate_tax, determine_tax_regime
from src.anomaly.anomaly_detector import detect_anomalies


def audit_document(extracted_fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main Audit Coordinator — acts as your automated GST accountant:

    1. Runs the Tax Engine to compute expected tax values from the regime
       (INTERSTATE/INTRASTATE), and fills any missing tax components if possible.
    2. Validates GSTIN formats for Supplier and Customer.
    3. Cross-checks all stated amounts against calculated values.
    4. Detects anomalies: missing fields, wrong amounts, math errors, etc.
    5. Calculates a transparent Risk Score (0–100).
    6. Assigns Audit Status: 'Passed', 'Needs Review', or 'Failed'.
    7. Generates plain-English explanations so a small business owner
       can understand exactly what's wrong — without needing a CA.
    """

    # -------------------------------------------------------------------
    # Step 1: Run the Tax Engine — determine regime and calculate expected values
    # -------------------------------------------------------------------
    supplier_gstin = extracted_fields.get("supplier_gstin")
    customer_gstin = extracted_fields.get("customer_gstin")
    place_of_supply = extracted_fields.get("place_of_supply")
    taxable = extracted_fields.get("taxable_amount")
    gst_rate = extracted_fields.get("gst_rate") or 18.0

    regime = determine_tax_regime(supplier_gstin, customer_gstin, place_of_supply)

    expected_tax = None
    if taxable is not None:
        expected_tax = calculate_tax(taxable, gst_rate, regime)

        # Auto-fill missing tax fields from tax engine if OCR didn't extract them
        if extracted_fields.get("igst") is None and extracted_fields.get("cgst") is None:
            if regime == "INTERSTATE":
                extracted_fields["igst"] = expected_tax["igst"]
            else:
                extracted_fields["cgst"] = expected_tax["cgst"]
                extracted_fields["sgst"] = expected_tax["sgst"]

        if extracted_fields.get("total_tax") is None:
            extracted_fields["total_tax"] = expected_tax["total_tax"]

        if extracted_fields.get("total_amount") is None:
            extracted_fields["total_amount"] = expected_tax["total_amount"]

    # -------------------------------------------------------------------
    # Step 2: Full tax validation (regime check + math check)
    # -------------------------------------------------------------------
    tax_validation = validate_tax(extracted_fields)

    # -------------------------------------------------------------------
    # Step 3: Validate GSTIN formats
    # -------------------------------------------------------------------
    supplier_gstin_val = validate_gstin_format(supplier_gstin)
    customer_gstin_val = validate_gstin_format(customer_gstin)

    # -------------------------------------------------------------------
    # Step 4: Detect anomalies
    # -------------------------------------------------------------------
    anomalies = detect_anomalies(extracted_fields, tax_validation)

    # -------------------------------------------------------------------
    # Step 5: Calculate Risk Score and Rationale
    # -------------------------------------------------------------------
    penalty_score = 0
    rationales: List[str] = []

    # GSTIN format issues — warn but softer penalty if it's an OCR issue
    if supplier_gstin and not supplier_gstin_val["valid"]:
        penalty_score += 10
        rationales.append(
            f"⚠️ Supplier GSTIN '{supplier_gstin}' may have an OCR reading error or is invalid. "
            f"Reason: {supplier_gstin_val['reason']}. Please verify with your original document."
        )

    # Tax regime info (informational, no penalty)
    rationales.append(
        f"📋 Transaction classified as {'Inter-State (IGST applies)' if regime == 'INTERSTATE' else 'Intra-State (CGST + SGST apply)'}."
    )

    # Anomaly penalties
    for anomaly in anomalies:
        sev = anomaly["severity"]
        if sev == "HIGH":
            penalty_score += 25
        elif sev == "MEDIUM":
            penalty_score += 10
        elif sev == "LOW":
            penalty_score += 5
        icon = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "ℹ️"}.get(sev, "•")
        rationales.append(f"{icon} [{sev}] {anomaly['issue']}")

    # Tax regime mismatch penalty
    if tax_validation.get("regime_status") != "Valid":
        penalty_score += 30

    risk_score = min(100, penalty_score)

    # -------------------------------------------------------------------
    # Step 6: Audit Status
    # -------------------------------------------------------------------
    if risk_score <= 15:
        audit_status = "Passed"
    elif risk_score <= 45:
        audit_status = "Needs Review"
    else:
        audit_status = "Failed"

    if risk_score == 0:
        rationales.append(
            "✅ All tax calculations, amounts, and mandatory fields are correct. "
            "This invoice is clear for ITC (Input Tax Credit) claim."
        )

    # ITC eligibility guidance for small business owners
    if audit_status == "Passed":
        itc_msg = "✅ Eligible — You can claim Input Tax Credit on this purchase."
    elif audit_status == "Needs Review":
        itc_msg = "⚠️ Hold — Verify discrepancies with your supplier before claiming ITC."
    else:
        itc_msg = "❌ Not Eligible — Invoice has critical errors. Contact your supplier for a corrected invoice."

    return {
        "audit_status": audit_status,
        "risk_score": risk_score,
        "tax_regime": regime,
        "expected_tax": expected_tax,
        "tax_validation": tax_validation,
        "supplier_gstin_validation": supplier_gstin_val,
        "customer_gstin_validation": customer_gstin_val,
        "anomalies": anomalies,
        "audit_rationale": rationales,
        "itc_eligibility": itc_msg
    }
