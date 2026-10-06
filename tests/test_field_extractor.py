import pytest
from src.extraction.field_extractor import (
    extract_fields,
    parse_number,
    parse_date,
    extract_gstins
)


def test_parse_number():
    assert parse_number("1,497.00") == 1497.0
    assert parse_number("₹ 3,988.00") == 3988.0
    assert parse_number(None) is None


def test_parse_date():
    assert parse_date("05-Mar-2020") == "2020-03-05"
    assert parse_date("05/03/2020") == "2020-03-05"
    assert parse_date("2020-03-05") == "2020-03-05"
    assert parse_date("29 Mar 2026") == "2026-03-29"
    assert parse_date("13 Apr 2026") == "2026-04-13"


def test_extract_gstins():
    text = "Supplier GSTIN: 24HDE7487RE5RT4 and Customer GSTIN: 07AOLCC1206D1ZG"
    gstins = extract_gstins(text)
    assert len(gstins) == 2
    assert "24HDE7487RE5RT4" in gstins
    assert "07AOLCC1206D1ZG" in gstins


def test_extract_fields_balaji_fruits():
    sample = """
    Balaji Dry Fruits. TAX INVOICE. ORIGINAL FOR RECIPIENT
    301, Janta Fruits Market, Jaipur, Rajasthan, Invoice No: S10
    302001 Invoice Date: 29 Mar 2026
    GSTIN: 1234ABCD12X1
    PAN NUMBER: ABCD12X1
    BILL TO
    Shyam Fruits
    GSTIN: XYZ12345XA12
    Place of Supply: Rajasthan

    Almond 8135010 1.0 KG 904.76 45.24 (5%) 950.00
    Cashew 8135010 1.0 Piece 857.14 42.86 (5%) 900.00
    Raisin 8135010 1.0 KG 428.57 21.43 (5%) 450.00

    Sub Total Taxable Amount: 2190.47
    CGST @ 2.50% 54.77
    SGST @ 2.50% 54.77
    Total Amount: 2300.00
    """
    fields = extract_fields(sample)
    assert fields["invoice_number"] == "S10"
    assert fields["invoice_date"] == "2026-03-29"
    assert fields["supplier_name"] == "Balaji Dry Fruits"
    assert fields["supplier_gstin"] == "1234ABCD12X1"
    assert fields["customer_gstin"] == "XYZ12345XA12"
    assert fields["taxable_amount"] == 2190.47
    assert fields["cgst"] == 54.77
    assert fields["sgst"] == 54.77
    assert fields["total_tax"] == 109.54
    assert fields["gst_rate"] == 5.0
    assert fields["total_amount"] == 2300.00


def test_extract_fields_full_text():
    sample_ocr_text = """
    GUJARAT FREIGHT TOOLS
    GSTIN: 24HDE7487RE5RT4
    Proforma No: 201
    Proforma Date: 05-Mar-2020
    M/S Kevin Motors
    GSTIN: 07AOLCC1206D1ZG
    Place of Supply: Delhi ( 07 )
    Reverse Charge: No
    Vehicle Number: GJ01KH2320

    1 Stanley Hammer 82052000 3.00 PCS 499.00 1,497.00 18.00 269.46 1,766.46
    2 Automatic Saw 8202 1.00 PCS 1883.00 1,883.00 18.00 338.94 2,221.94

    Taxable Value: 3,380.00
    Add: IGST: 608.40
    Total Amount After Tax: 3,988.00
    Amount in Words: THREE THOUSAND NINE HUNDRED AND EIGHTY-EIGHT RUPEES ONLY
    Bank Name: State Bank of India
    Bank Account Number: 200000004512
    IFSC: SBIN0000488
    """
    fields = extract_fields(sample_ocr_text)

    assert fields["supplier_gstin"] == "24HDE7487RE5RT4"
    assert fields["customer_gstin"] == "07AOLCC1206D1ZG"
    assert fields["proforma_number"] == "201"
    assert fields["invoice_date"] == "2020-03-05"
    assert fields["taxable_amount"] == 3380.0
    assert fields["igst"] == 608.4
    assert fields["total_amount"] == 3988.0
    assert fields["vehicle_number"] == "GJ01KH2320"
    assert fields["bank_details"]["account_number"] == "200000004512"
    assert fields["bank_details"]["ifsc"] == "SBIN0000488"
    assert len(fields["items"]) == 2


def test_extract_fields_aarav_traders():
    ocr_text = """
    ORIGINAL FOR RECIPIENT
    y. Aarav Traders
    Aarav Traders Invoice No. : INV/2026/001
    12, Industrial Area, Sitapura TAX INVOICE Invoice Date =: 05 Mar 2026
    Jaipur - 302022, Rajasthan, india (Under Section 31 of CGST Act, 2017) Due Date 1 20 Mar 2026
    Ph: +91 141 4056789 | Email: info@aaravtraders.in
    ORIGINAL FOR RECIPIENT Place of Supply : Rajasthan (08)
    GSTIN: 08AABCA1234F1Z5 Reverse Charge : No
    BILL TO (CUSTOMER DETAILS) SHIP TO (DELIVERY ADDRESS)
    Shree Retail Mart Pvt. Ltd. Shree Retail Mart Pvt. Ltd
    14, MI Road, Jaipur - 302001 14, MI Road, Jaipur - 302001
    Rajasthan, India Rajasthan, India
    GSTIN: 08AAEFS9876H121

    1 | Almonds (California) 08021210 10 KG 800.00 8,000.00 5% 200.00 200.00 8,400.00
    2 | Cashew Nuts (W320) 08013220 5 KG 1,000.00 5,000.00 5% 125.00 125.00 5,250.00
    3 Raisins (Black) 08062000 10 KG 300.00 3,000.00 5% 75.00 75.00 3,150.00

    Total Taxable Amount (₹) 16,000.00
    Remarks: Goods sold are of standard quality and as per quotation.
    CGST @ 2.5% (%) 400.00
    SGST @ 2.5% (8) 400.00
    Total GST Amount (₹) 800.00
    Grand Total (₹) 16,800.00
    Amount in Words: INR Sixteen Thousand Eight Hundred Only
    """
    fields = extract_fields(ocr_text)

    assert fields["invoice_number"] == "INV/2026/001"
    assert fields["invoice_date"] == "2026-03-05"
    assert fields["supplier_name"] == "Aarav Traders"
    assert fields["supplier_gstin"] == "08AABCA1234F1Z5"
    assert fields["customer_name"] == "Shree Retail Mart Pvt. Ltd."
    assert fields["customer_gstin"] == "08AAEFS9876H121"
    assert fields["taxable_amount"] == 16000.0
    assert fields["cgst"] == 400.0
    assert fields["sgst"] == 400.0
    assert fields["total_tax"] == 800.0
    assert fields["total_amount"] == 16800.0
    assert len(fields["items"]) == 3

