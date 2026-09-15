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


def test_extract_gstins():
    text = "Supplier GSTIN: 24HDE7487RE5RT4 and Customer GSTIN: 07AOLCC1206D1ZG"
    gstins = extract_gstins(text)
    assert len(gstins) == 2
    assert "24HDE7487RE5RT4" in gstins
    assert "07AOLCC1206D1ZG" in gstins


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
