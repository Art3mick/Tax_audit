import json
import pandas as pd
import streamlit as st
from pathlib import Path

from src.document.preprocessing import process_document
from src.ocr.ocr_engine import extract_text, extract_text_from_pdf_stream
from src.extraction.field_extractor import extract_fields
from src.audit.audit_engine import audit_document
from src.database.db_manager import (
    save_audit_record,
    get_all_audit_records,
    get_summary_stats,
    check_duplicate_invoice,
    delete_audit_record,
    clear_all_audit_records
)

# ─────────────────────────────────────────────
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="GST Invoice Checker — Small Business Assistant",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/invoice.png", width=80)
    st.title("🧾 GST Invoice Checker")
    st.caption("Your automated tax assistant — no CA needed")

    st.markdown("---")
    st.markdown("""
**What this tool does for you:**
- 📤 Reads your invoice automatically
- 🔢 Checks if the GST amount is calculated correctly
- 🗺️ Detects if IGST vs CGST/SGST is applied correctly
- 🚨 Flags missing information or calculation errors
- 💰 Tells you if you can claim Input Tax Credit (ITC)
- 🗄️ Saves every audit for your records
""")
    st.markdown("---")
    st.info(
        "**100% Private & Local**\n\n"
        "Your documents are never sent to the internet. "
        "All processing happens on your computer."
    )
    st.markdown("---")
    st.caption("Supports: Invoice, Proforma, Challan, Bill, Receipt (JPG, PNG, PDF)")


# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────
tab_single, tab_bulk, tab_history = st.tabs([
    "🔍 Check an Invoice",
    "📦 Check Many Invoices (Bulk)",
    "📊 My Audit Records"
])


# ══════════════════════════════════════════════════════════════════
# TAB 1 — SINGLE INVOICE CHECK
# ══════════════════════════════════════════════════════════════════
with tab_single:
    st.header("Check Your Invoice")
    st.write(
        "Upload any invoice image or PDF below. The system will read it, "
        "check the GST calculations, and tell you if anything looks wrong."
    )

    uploaded_file = st.file_uploader(
        "📎 Upload Invoice (JPG, PNG, WebP, PDF)",
        type=["png", "jpg", "jpeg", "webp", "pdf"],
        key="single_uploader"
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        file_name = uploaded_file.name
        file_type = uploaded_file.type

        # Save uploaded file
        saved_path = UPLOAD_DIR / file_name
        with open(saved_path, "wb") as f:
            f.write(file_bytes)

        st.success(f"✅ File received: **{file_name}**")

        # ── PROCESS DOCUMENT ──────────────────────────────────────
        with st.spinner("🔍 Reading your document... (this may take a few seconds)"):
            pages = process_document(file_bytes, file_type)

            ocr_texts = []

            # For PDFs: try direct digital text extraction first
            if "pdf" in file_type.lower():
                digital_text = extract_text_from_pdf_stream(file_bytes)
                if len(digital_text.strip()) > 50:
                    ocr_texts.append(digital_text)

            # Fallback to image OCR for all pages
            if not ocr_texts:
                for page in pages:
                    txt = extract_text(page["processed"], page.get("gray"))
                    if txt.strip():
                        ocr_texts.append(txt)

            combined_text = "\n\n".join(ocr_texts)

        # ── DOCUMENT PREVIEW ──────────────────────────────────────
        st.markdown("---")
        col_orig, col_proc = st.columns(2)
        with col_orig:
            st.markdown("**Your Document**")
            st.image(pages[0]["original"], channels="BGR", use_container_width=True)
        with col_proc:
            st.markdown("**How the system sees it (for text reading)**")
            st.image(pages[0]["processed"], channels="GRAY", use_container_width=True)

        # ── EXTRACT FIELDS & AUDIT ────────────────────────────────
        extracted = extract_fields(combined_text)
        audit = audit_document(extracted)

        # ── DUPLICATE WARNING ─────────────────────────────────────
        dup = check_duplicate_invoice(
            extracted.get("supplier_gstin"),
            extracted.get("invoice_number")
        )
        if dup:
            st.warning(
                f"⚠️ **Heads up!** This invoice (#{extracted.get('invoice_number')} from "
                f"GSTIN {extracted.get('supplier_gstin')}) was already checked on "
                f"**{dup['upload_timestamp'][:10]}** (Record ID: `{dup['audit_id']}`). "
                "Make sure you're not paying or claiming ITC twice!"
            )

        # ══════════════════════════════════════════════════════════
        # AUDIT RESULT CARD — TOP LEVEL SUMMARY
        # ══════════════════════════════════════════════════════════
        st.markdown("---")
        status = audit["audit_status"]
        score = audit["risk_score"]

        if status == "Passed":
            st.success(f"## ✅ Invoice OK — No Issues Found")
        elif status == "Needs Review":
            st.warning(f"## ⚠️ Invoice Needs Attention — Some Issues Found")
        else:
            st.error(f"## 🚨 Invoice Has Problems — Action Required")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status", status)
        c2.metric(
            "Risk Score",
            f"{score}/100",
            delta="Low Risk ✅" if score <= 15 else ("Medium Risk ⚠️" if score <= 45 else "High Risk 🚨"),
            delta_color="off"
        )
        c3.metric("Tax Type Detected", audit.get("tax_regime", "—"))
        c4.metric("ITC Claim", "Yes ✅" if status == "Passed" else ("Hold ⚠️" if status == "Needs Review" else "No ❌"))

        # ITC box — explain in plain language
        st.info(f"**Input Tax Credit (ITC):** {audit['itc_eligibility']}")

        # ══════════════════════════════════════════════════════════
        # PLAIN ENGLISH AUDIT NOTES
        # ══════════════════════════════════════════════════════════
        st.markdown("---")
        st.subheader("📋 What We Found")
        for note in audit["audit_rationale"]:
            if "🚨" in note or "HIGH" in note:
                st.error(note)
            elif "⚠️" in note or "MEDIUM" in note:
                st.warning(note)
            elif "✅" in note:
                st.success(note)
            else:
                st.info(note)

        # ══════════════════════════════════════════════════════════
        # INVOICE INFORMATION EXTRACTED
        # ══════════════════════════════════════════════════════════
        st.markdown("---")
        st.subheader("📄 Invoice Details Extracted")

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            st.markdown("**🏭 Seller (Supplier)**")
            st.write(f"• Name: **{extracted.get('supplier_name') or 'Not found'}**")
            st.write(f"• GSTIN: `{extracted.get('supplier_gstin') or 'Not found'}`")
            s_valid = audit.get("supplier_gstin_validation", {})
            if s_valid.get("valid"):
                st.caption(f"✅ GSTIN valid — {s_valid.get('state_name', '')}")
            elif extracted.get("supplier_gstin"):
                st.caption(f"⚠️ GSTIN may have OCR errors — verify manually")

        with col_b:
            st.markdown("**🛒 Buyer (Customer)**")
            st.write(f"• Name: **{extracted.get('customer_name') or 'Not found'}**")
            st.write(f"• GSTIN: `{extracted.get('customer_gstin') or 'Not found'}`")
            c_valid = audit.get("customer_gstin_validation", {})
            if c_valid.get("valid"):
                st.caption(f"✅ GSTIN valid — {c_valid.get('state_name', '')}")
            elif extracted.get("customer_gstin"):
                st.caption(f"⚠️ GSTIN may have OCR errors — verify manually")
            st.write(f"• Place of Supply: **{extracted.get('place_of_supply') or 'Not found'}**")

        with col_c:
            st.markdown("**📋 Invoice Info**")
            inv_label = "Invoice #" if not extracted.get("proforma_number") else "Proforma #"
            st.write(f"• {inv_label}: **{extracted.get('invoice_number') or 'Not found'}**")
            st.write(f"• Date: **{extracted.get('invoice_date') or 'Not found'}**")
            if extracted.get("challan_number"):
                st.write(f"• Challan #: **{extracted['challan_number']}**")
            if extracted.get("vehicle_number"):
                st.write(f"• Vehicle: **{extracted['vehicle_number']}**")
            if extracted.get("transporter_name"):
                st.write(f"• Transporter: **{extracted['transporter_name']}**")
            if extracted.get("reverse_charge") and extracted["reverse_charge"] != "Not detected":
                st.write(f"• Reverse Charge: **{extracted['reverse_charge']}**")

        # ══════════════════════════════════════════════════════════
        # TAX AMOUNTS — WHAT WAS ON INVOICE vs WHAT IT SHOULD BE
        # ══════════════════════════════════════════════════════════
        st.markdown("---")
        st.subheader("🧮 GST Calculation Check")
        st.caption(
            "This table compares the amounts printed on your invoice against what they "
            "should be based on the tax rate. A mismatch means the invoice may have an error."
        )

        exp_tax = audit.get("expected_tax")
        recon_rows = [
            {
                "Amount Type": "Taxable Value (before GST)",
                "On Your Invoice": f"₹{extracted.get('taxable_amount') or 0:,.2f}",
                "Should Be": f"₹{exp_tax['taxable_amount']:,.2f}" if exp_tax else "—",
                "Match?": "✅" if exp_tax and abs((extracted.get("taxable_amount") or 0) - exp_tax["taxable_amount"]) < 1 else "⚠️"
            },
            {
                "Amount Type": f"CGST ({(extracted.get('gst_rate') or 18)/2:.1f}%)" ,
                "On Your Invoice": f"₹{extracted.get('cgst') or 0:,.2f}",
                "Should Be": f"₹{exp_tax['cgst']:,.2f}" if exp_tax else "—",
                "Match?": "✅" if exp_tax and abs((extracted.get("cgst") or 0) - exp_tax["cgst"]) < 1 else ("N/A" if exp_tax and exp_tax["cgst"] == 0 else "⚠️")
            },
            {
                "Amount Type": f"SGST ({(extracted.get('gst_rate') or 18)/2:.1f}%)",
                "On Your Invoice": f"₹{extracted.get('sgst') or 0:,.2f}",
                "Should Be": f"₹{exp_tax['sgst']:,.2f}" if exp_tax else "—",
                "Match?": "✅" if exp_tax and abs((extracted.get("sgst") or 0) - exp_tax["sgst"]) < 1 else ("N/A" if exp_tax and exp_tax["sgst"] == 0 else "⚠️")
            },
            {
                "Amount Type": f"IGST ({extracted.get('gst_rate') or 18:.1f}%)",
                "On Your Invoice": f"₹{extracted.get('igst') or 0:,.2f}",
                "Should Be": f"₹{exp_tax['igst']:,.2f}" if exp_tax else "—",
                "Match?": "✅" if exp_tax and abs((extracted.get("igst") or 0) - exp_tax["igst"]) < 1 else ("N/A" if exp_tax and exp_tax["igst"] == 0 else "⚠️")
            },
            {
                "Amount Type": "Total Tax",
                "On Your Invoice": f"₹{extracted.get('total_tax') or 0:,.2f}",
                "Should Be": f"₹{exp_tax['total_tax']:,.2f}" if exp_tax else "—",
                "Match?": "✅" if exp_tax and abs((extracted.get("total_tax") or 0) - exp_tax["total_tax"]) < 1 else "⚠️"
            },
            {
                "Amount Type": "Grand Total (incl. GST)",
                "On Your Invoice": f"₹{extracted.get('total_amount') or 0:,.2f}",
                "Should Be": f"₹{exp_tax['total_amount']:,.2f}" if exp_tax else "—",
                "Match?": "✅" if exp_tax and abs((extracted.get("total_amount") or 0) - exp_tax["total_amount"]) < 1 else "⚠️"
            },
        ]
        st.table(pd.DataFrame(recon_rows))

        if extracted.get("amount_in_words"):
            st.caption(f"**Amount in Words:** {extracted['amount_in_words']}")

        # ── Line Items Table ──────────────────────────────────────
        if extracted.get("items"):
            st.markdown("---")
            st.subheader("📦 Items on Invoice")
            df_items = pd.DataFrame(extracted["items"])
            cols_to_show = [c for c in ["sr_no", "description", "hsn_sac", "quantity", "unit", "rate", "taxable_amount", "tax_rate", "total_amount"] if c in df_items.columns]
            st.dataframe(df_items[cols_to_show], use_container_width=True)

        # ── Bank Details ──────────────────────────────────────────
        bank = extracted.get("bank_details", {})
        if any(bank.get(k) for k in ["bank_name", "account_number", "ifsc"]):
            st.markdown("---")
            st.subheader("🏦 Supplier's Bank Details")
            bc1, bc2, bc3 = st.columns(3)
            bc1.write(f"Bank: **{bank.get('bank_name') or '—'}**")
            bc2.write(f"Account: **{bank.get('account_number') or '—'}**")
            bc3.write(f"IFSC: **{bank.get('ifsc') or '—'}**")

        # ── Raw OCR Text (expandable) ─────────────────────────────
        with st.expander("🔎 Raw OCR Text (for debugging)"):
            st.text_area("OCR Output", combined_text, height=200)

        # ── SAVE TO DATABASE ──────────────────────────────────────
        st.markdown("---")
        col_save1, col_save2 = st.columns([1, 3])
        with col_save1:
            if st.button("💾 Save to My Records", type="primary"):
                audit_id = save_audit_record(
                    file_name=file_name,
                    file_bytes=file_bytes,
                    file_type=file_type,
                    extracted_fields=extracted,
                    audit_result=audit
                )
                st.success(f"Saved! Record ID: `{audit_id}`")
        with col_save2:
            st.caption("Save this audit result to your records for future reference and GST filing.")


# ══════════════════════════════════════════════════════════════════
# TAB 2 — BULK INVOICE CHECK
# ══════════════════════════════════════════════════════════════════
with tab_bulk:
    st.header("📦 Check Multiple Invoices at Once")
    st.write(
        "Got a stack of purchase invoices from your vendors? "
        "Upload them all at once and get a full GST audit summary — "
        "perfect for monthly ITC reconciliation."
    )

    bulk_files = st.file_uploader(
        "📎 Upload Multiple Invoices",
        type=["png", "jpg", "jpeg", "pdf"],
        accept_multiple_files=True,
        key="bulk_uploader"
    )

    if bulk_files:
        st.info(f"**{len(bulk_files)} file(s) selected.** Click the button below to start.")

        if st.button("🚀 Run Bulk Audit Now", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            bulk_results = []
            total_taxable = 0.0
            total_tax = 0.0

            for idx, bfile in enumerate(bulk_files, start=1):
                status_text.text(f"Processing {idx}/{len(bulk_files)}: {bfile.name}...")
                b_bytes = bfile.getvalue()

                try:
                    pages = process_document(b_bytes, bfile.type)
                    texts = []
                    if "pdf" in bfile.type.lower():
                        d_txt = extract_text_from_pdf_stream(b_bytes)
                        if len(d_txt.strip()) > 50:
                            texts.append(d_txt)
                    if not texts:
                        for p in pages:
                            texts.append(extract_text(p["processed"], p.get("gray")))

                    ext_f = extract_fields("\n\n".join(texts))
                    aud_r = audit_document(ext_f)

                    aid = save_audit_record(
                        file_name=bfile.name,
                        file_bytes=b_bytes,
                        file_type=bfile.type,
                        extracted_fields=ext_f,
                        audit_result=aud_r
                    )

                    t_val = ext_f.get("taxable_amount") or 0.0
                    t_tax = ext_f.get("total_tax") or 0.0
                    total_taxable += t_val
                    total_tax += t_tax

                    bulk_results.append({
                        "Record ID": aid,
                        "File": bfile.name,
                        "Supplier": ext_f.get("supplier_name") or "Unknown",
                        "Invoice #": ext_f.get("invoice_number") or "—",
                        "Date": ext_f.get("invoice_date") or "—",
                        "Taxable Value": f"₹{t_val:,.2f}",
                        "Total GST": f"₹{t_tax:,.2f}",
                        "Grand Total": f"₹{(ext_f.get('total_amount') or 0):,.2f}",
                        "Risk Score": aud_r["risk_score"],
                        "Status": aud_r["audit_status"],
                        "ITC": "✅ Eligible" if aud_r["audit_status"] == "Passed" else "⚠️ Review"
                    })
                except Exception as e:
                    bulk_results.append({
                        "Record ID": "ERROR",
                        "File": bfile.name,
                        "Supplier": "—",
                        "Invoice #": "—",
                        "Date": "—",
                        "Taxable Value": "—",
                        "Total GST": "—",
                        "Grand Total": "—",
                        "Risk Score": 100,
                        "Status": "Failed",
                        "ITC": f"❌ Error: {str(e)}"
                    })

                progress_bar.progress(idx / len(bulk_files))

            status_text.empty()
            progress_bar.empty()

            st.success(f"✅ Bulk audit complete for **{len(bulk_files)}** invoice(s)!")

            # Summary metrics
            passed = sum(1 for r in bulk_results if r["Status"] == "Passed")
            review = sum(1 for r in bulk_results if r["Status"] == "Needs Review")
            failed = sum(1 for r in bulk_results if r["Status"] == "Failed")

            mc1, mc2, mc3, mc4, mc5 = st.columns(5)
            mc1.metric("Total Invoices", len(bulk_results))
            mc2.metric("✅ Passed", passed)
            mc3.metric("⚠️ Review Needed", review)
            mc4.metric("❌ Failed", failed)
            mc5.metric("Total GST Audited", f"₹{total_tax:,.2f}")

            st.markdown("---")
            df_bulk = pd.DataFrame(bulk_results)
            st.dataframe(df_bulk, use_container_width=True)

            csv = df_bulk.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Bulk Audit Report (CSV)",
                csv,
                "bulk_gst_audit_report.csv",
                "text/csv"
            )


# ══════════════════════════════════════════════════════════════════
# TAB 3 — AUDIT HISTORY / DATABASE
# ══════════════════════════════════════════════════════════════════
with tab_history:
    st.header("📊 My Audit Records")
    st.write(
        "All your past invoice audits are stored here. "
        "Use this for GST filing, ITC reconciliation, or accounting review."
    )

    stats = get_summary_stats()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Invoices Checked", stats["total_documents"])
    m2.metric("✅ Passed", stats["passed_documents"])
    m3.metric("⚠️ Needs Review", stats["needs_review_documents"])
    m4.metric("❌ Failed Audit", stats["failed_documents"])
    m5.metric("Total GST Audited", f"₹{stats['total_tax_audited']:,.2f}")

    st.markdown("---")

    col_f1, col_f2 = st.columns(2)
    status_filter = col_f1.selectbox(
        "Filter by Status",
        ["All", "Passed", "Needs Review", "Failed"]
    )

    records = get_all_audit_records()

    if records:
        df_rec = pd.DataFrame(records)

        if status_filter != "All":
            df_rec = df_rec[df_rec["audit_status"] == status_filter]

        display_cols = [
            "audit_id", "upload_timestamp", "file_name", "supplier_name",
            "supplier_gstin", "invoice_number", "invoice_date",
            "taxable_amount", "total_tax", "total_amount",
            "risk_score", "audit_status"
        ]
        available_cols = [c for c in display_cols if c in df_rec.columns]

        # Rename for readability
        df_display = df_rec[available_cols].rename(columns={
            "audit_id": "Record ID",
            "upload_timestamp": "Date Checked",
            "file_name": "File",
            "supplier_name": "Supplier",
            "supplier_gstin": "Supplier GSTIN",
            "invoice_number": "Invoice #",
            "invoice_date": "Invoice Date",
            "taxable_amount": "Taxable (₹)",
            "total_tax": "GST (₹)",
            "total_amount": "Grand Total (₹)",
            "risk_score": "Risk Score",
            "audit_status": "Status"
        })

        st.dataframe(df_display, use_container_width=True)

        st.markdown("---")
        st.subheader("⚙️ Record Management & Deletion")

        col_del1, col_del2 = st.columns(2)

        with col_del1:
            st.markdown("**Delete Specific Record**")
            record_options = [f"{r['audit_id']} | {r.get('supplier_name') or 'Unknown'} ({r.get('invoice_number') or 'No Inv#'})" for r in records]
            selected_to_delete = st.selectbox(
                "Select Record to Delete",
                options=record_options,
                key="select_del_record"
            )
            if st.button("🗑️ Delete Selected Record", type="secondary"):
                target_id = selected_to_delete.split(" | ")[0].strip()
                if delete_audit_record(target_id):
                    st.success(f"Record `{target_id}` deleted successfully!")
                    st.rerun()
                else:
                    st.error("Failed to delete record.")

        with col_del2:
            st.markdown("**Clear Entire Database**")
            with st.expander("⚠️ Danger Zone: Clear All Records"):
                st.warning("This will permanently delete all stored audit records from the database.")
                confirm_clear = st.checkbox("I understand this action cannot be undone", key="confirm_clear_all")
                if st.button("🗑️ Clear All Records Now", type="primary", disabled=not confirm_clear):
                    clear_all_audit_records()
                    st.success("All audit records deleted!")
                    st.rerun()

        st.markdown("---")
        csv_data = df_display.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download All Records (CSV)",
            csv_data,
            "my_gst_audit_records.csv",
            "text/csv"
        )
    else:
        st.info(
            "No records yet. Check an invoice in the **'Check an Invoice'** tab "
            "and click **'Save to My Records'** to start building your audit history."
        )