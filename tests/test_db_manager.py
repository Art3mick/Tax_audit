import pytest
from src.database.db_manager import (
    init_db,
    save_audit_record,
    get_all_audit_records,
    get_summary_stats,
    delete_audit_record,
    clear_all_audit_records
)


def test_db_operations():
    init_db()

    sample_fields = {
        "supplier_name": "Gujarat Freight Tools",
        "supplier_gstin": "24HDE7487RE5RT4",
        "customer_name": "Kevin Motors",
        "customer_gstin": "07AOLCC1206D1ZG",
        "invoice_number": "INV-TEST-001",
        "invoice_date": "2020-03-05",
        "taxable_amount": 1000.0,
        "gst_rate": 18.0,
        "igst": 180.0,
        "total_tax": 180.0,
        "total_amount": 1180.0,
        "raw_text": "Sample test text"
    }

    sample_audit = {
        "audit_status": "Passed",
        "risk_score": 0,
        "tax_validation": {"status": "Valid"},
        "anomalies": []
    }

    file_bytes = b"fake_file_content_12345"
    audit_id = save_audit_record(
        file_name="test_invoice.jpg",
        file_bytes=file_bytes,
        file_type="image/jpeg",
        extracted_fields=sample_fields,
        audit_result=sample_audit
    )

    assert audit_id.startswith("AUD-")

    records = get_all_audit_records()
    assert len(records) > 0

    stats = get_summary_stats()
    assert stats["total_documents"] > 0

    # Test single record deletion
    deleted = delete_audit_record(audit_id)
    assert deleted is True
