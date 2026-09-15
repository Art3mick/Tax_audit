import pytest
from src.audit.audit_engine import audit_document


def test_audit_document_passed():
    fields = {
        "invoice_number": "201",
        "invoice_date": "2020-03-05",
        "supplier_gstin": "24HDE7487RE5RT4",
        "customer_gstin": "07AOLCC1206D1ZG",
        "taxable_amount": 3380.00,
        "gst_rate": 18.0,
        "igst": 608.40,
        "total_tax": 608.40,
        "total_amount": 3988.00,
        "items": []
    }
    audit = audit_document(fields)
    assert audit["audit_status"] == "Passed"
    assert audit["risk_score"] <= 15
    assert "Eligible" in audit["itc_eligibility"]


def test_audit_document_failed():
    fields = {
        "invoice_number": None,
        "invoice_date": None,
        "supplier_gstin": None,
        "taxable_amount": 5000.00,
        "total_amount": 1000.00,  # Invalid: taxable > total
        "items": []
    }
    audit = audit_document(fields)
    assert audit["audit_status"] == "Failed"
    assert audit["risk_score"] > 45
    assert len(audit["anomalies"]) > 0
