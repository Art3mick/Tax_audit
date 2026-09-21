from typing import Dict, Any, List
from src.tax.tax_engine import validate_tax, validate_gstin_format, calculate_tax, determine_tax_regime
from src.anomaly.anomaly_detector import detect_anomalies
from src.anomaly.ml_anomaly_detector import GSTIsolationForestDetector

# Global ML detector instance (auto-pretrains on synthetic baseline if no DB records yet)
_ml_detector = GSTIsolationForestDetector()


def audit_document(extracted_fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main Audit Coordinator — acts as your automated GST accountant:

    1. Runs the Tax Engine to compute expected tax values from the regime
       (INTERSTATE/INTRASTATE).
    2. Validates GSTIN formats for Supplier and Customer.
    3. Cross-checks all stated amounts against calculated values.
    4. Detects rule-based anomalies (missing fields, wrong amounts, math errors).
    5. Runs Unsupervised Isolation Forest ML model to detect statistical outliers.
    6. Calculates a transparent Risk Score (0–100).
    7. Assigns Audit Status: 'Passed', 'Needs Review', or 'Failed'.
    8. Generates plain-English explanations for small business owners.
    """

    # -------------------------------------------------------------------
    # Step 1: Run the Tax Engine — determine regime and calculate expected values
    # -------------------------------------------------------------------
    supplier_gstin = extracted_fields.get("supplier_gstin")
    customer_gstin = extracted_fields.get("customer_gstin")
    place_of_supply = extracted_fields.get("place_of_supply")
    taxable = extracted_fields.get("taxable_amount")
    gst_rate = extracted_fields.get("gst_rate")
    if gst_rate is None and taxable and extracted_fields.get("total_tax") and taxable > 0:
        gst_rate = round((extracted_fields["total_tax"] / taxable) * 100, 2)
    if gst_rate is None:
        gst_rate = 18.0

    regime = determine_tax_regime(supplier_gstin, customer_gstin, place_of_supply)

    expected_tax = None
    if taxable is not None:
        expected_tax = calculate_tax(taxable, gst_rate, regime)

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
    # Step 4: Detect Rule-Based Anomalies & ML Statistical Anomalies
    # -------------------------------------------------------------------
    anomalies = detect_anomalies(extracted_fields, tax_validation)
    
    # Run Isolation Forest ML Predictor
    ml_res = _ml_detector.predict(extracted_fields)

    # -------------------------------------------------------------------
    # Step 5: Calculate Risk Score and Rationale
    # -------------------------------------------------------------------
    penalty_score = 0
    rationales: List[str] = []

    # GSTIN format issues
    if supplier_gstin and not supplier_gstin_val["valid"]:
        penalty_score += 10
        rationales.append(
            f"⚠️ Supplier GSTIN '{supplier_gstin}' may have an OCR reading error or is invalid. "
            f"Reason: {supplier_gstin_val['reason']}. Please verify with your original document."
        )

    # Tax regime info
    rationales.append(
        f"📋 Transaction classified as {'Inter-State (IGST applies)' if regime == 'INTERSTATE' else 'Intra-State (CGST + SGST apply)'}."
    )

    # ML Anomaly rationale note
    rationales.append(ml_res["ml_rationale"])
    if ml_res["is_anomaly"]:
        penalty_score += 15

    # Rule Anomaly penalties
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

    # ITC eligibility guidance
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
        "ml_result": ml_res,
        "audit_rationale": rationales,
        "itc_eligibility": itc_msg
    }
