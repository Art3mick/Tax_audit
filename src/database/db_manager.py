import sqlite3
import json
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = Path("data/audit_database.db")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Creates audit_records table if it doesn't exist.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_records (
                audit_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_hash TEXT,
                file_type TEXT,
                upload_timestamp TEXT NOT NULL,
                supplier_name TEXT,
                supplier_gstin TEXT,
                customer_name TEXT,
                customer_gstin TEXT,
                invoice_number TEXT,
                invoice_date TEXT,
                taxable_amount REAL,
                gst_rate REAL,
                cgst REAL,
                sgst REAL,
                igst REAL,
                total_tax REAL,
                total_amount REAL,
                extracted_fields_json TEXT,
                raw_ocr_text TEXT,
                tax_validation_json TEXT,
                anomalies_json TEXT,
                risk_score INTEGER,
                audit_status TEXT,
                processing_errors TEXT
            )
        """)
        conn.commit()


# Auto-initialize DB on module load
init_db()


def compute_file_hash(file_bytes: bytes) -> str:
    """
    Computes SHA-256 hash of uploaded file to prevent duplicate processing.
    """
    return hashlib.sha256(file_bytes).hexdigest()


def check_duplicate_invoice(supplier_gstin: Optional[str], invoice_number: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Checks if an invoice with the same supplier GSTIN and invoice number already exists in DB.
    """
    if not supplier_gstin or not invoice_number:
        return None
        
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM audit_records 
            WHERE LOWER(supplier_gstin) = LOWER(?) AND LOWER(invoice_number) = LOWER(?)
            ORDER BY upload_timestamp DESC LIMIT 1
        """, (supplier_gstin.strip(), invoice_number.strip()))
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None


def save_audit_record(
    file_name: str,
    file_bytes: bytes,
    file_type: str,
    extracted_fields: Dict[str, Any],
    audit_result: Dict[str, Any],
    processing_errors: Optional[str] = None
) -> str:
    """
    Saves a complete audit record into SQLite database.
    Returns the generated audit_id.
    """
    audit_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
    file_hash = compute_file_hash(file_bytes)
    timestamp = datetime.now().isoformat()

    taxable = extracted_fields.get("taxable_amount")
    gst_rate = extracted_fields.get("gst_rate")
    cgst = extracted_fields.get("cgst")
    sgst = extracted_fields.get("sgst")
    igst = extracted_fields.get("igst")
    total_tax = extracted_fields.get("total_tax")
    total_amount = extracted_fields.get("total_amount")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_records (
                audit_id, file_name, file_hash, file_type, upload_timestamp,
                supplier_name, supplier_gstin, customer_name, customer_gstin,
                invoice_number, invoice_date, taxable_amount, gst_rate,
                cgst, sgst, igst, total_tax, total_amount,
                extracted_fields_json, raw_ocr_text, tax_validation_json,
                anomalies_json, risk_score, audit_status, processing_errors
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            audit_id,
            file_name,
            file_hash,
            file_type,
            timestamp,
            extracted_fields.get("supplier_name"),
            extracted_fields.get("supplier_gstin"),
            extracted_fields.get("customer_name"),
            extracted_fields.get("customer_gstin"),
            extracted_fields.get("invoice_number"),
            extracted_fields.get("invoice_date"),
            taxable,
            gst_rate,
            cgst,
            sgst,
            igst,
            total_tax,
            total_amount,
            json.dumps(extracted_fields, default=str),
            extracted_fields.get("raw_text", ""),
            json.dumps(audit_result.get("tax_validation"), default=str),
            json.dumps(audit_result.get("anomalies"), default=str),
            audit_result.get("risk_score", 0),
            audit_result.get("audit_status", "Needs Review"),
            processing_errors or ""
        ))
        conn.commit()

    return audit_id


def get_all_audit_records() -> List[Dict[str, Any]]:
    """
    Fetches all audit records sorted by upload timestamp descending.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_records ORDER BY upload_timestamp DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def delete_audit_record(audit_id: str) -> bool:
    """
    Deletes a single audit record from SQLite database by audit_id.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_records WHERE audit_id = ?", (audit_id,))
        conn.commit()
        return cursor.rowcount > 0


def clear_all_audit_records() -> bool:
    """
    Clears all audit records from SQLite database.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_records")
        conn.commit()
        return True


def get_summary_stats() -> Dict[str, Any]:
    """
    Computes dashboard summary stats across all audited documents.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as total FROM audit_records")
        total_docs = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as passed FROM audit_records WHERE audit_status = 'Passed'")
        passed_docs = cursor.fetchone()["passed"]

        cursor.execute("SELECT COUNT(*) as review FROM audit_records WHERE audit_status = 'Needs Review'")
        review_docs = cursor.fetchone()["review"]

        cursor.execute("SELECT COUNT(*) as failed FROM audit_records WHERE audit_status = 'Failed'")
        failed_docs = cursor.fetchone()["failed"]

        cursor.execute("SELECT SUM(taxable_amount) as total_taxable, SUM(total_tax) as total_tax_amt, SUM(total_amount) as grand_total FROM audit_records")
        sum_row = cursor.fetchone()

        return {
            "total_documents": total_docs,
            "passed_documents": passed_docs,
            "needs_review_documents": review_docs,
            "failed_documents": failed_docs,
            "total_taxable_value": sum_row["total_taxable"] or 0.0,
            "total_tax_audited": sum_row["total_tax_amt"] or 0.0,
            "total_grand_amount": sum_row["grand_total"] or 0.0
        }
