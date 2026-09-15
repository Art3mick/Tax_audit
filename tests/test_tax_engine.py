import pytest
from src.tax.tax_engine import (
    get_state_from_gstin,
    validate_gstin_format,
    determine_tax_regime,
    calculate_tax,
    validate_tax
)


def test_get_state_from_gstin():
    gujarat = get_state_from_gstin("24HDE7487RE5RT4")
    assert gujarat is not None
    assert gujarat["code"] == "24"
    assert gujarat["state_name"] == "Gujarat"

    delhi = get_state_from_gstin("07AOLCC1206D1ZG")
    assert delhi is not None
    assert delhi["code"] == "07"
    assert delhi["state_name"] == "Delhi"

    assert get_state_from_gstin(None) is None


def test_validate_gstin_format():
    val = validate_gstin_format("24ABCDE1234F1Z5")
    assert val["valid"] is True
    assert val["state_code"] == "24"

    invalid_val = validate_gstin_format("123INVALID")
    assert invalid_val["valid"] is False


def test_determine_tax_regime():
    # Gujarat to Delhi = INTERSTATE
    regime = determine_tax_regime("24HDE7487RE5RT4", "07AOLCC1206D1ZG")
    assert regime == "INTERSTATE"

    # Gujarat to Gujarat = INTRASTATE
    regime_intra = determine_tax_regime("24HDE7487RE5RT4", "24AOLCC1206D1ZG")
    assert regime_intra == "INTRASTATE"


def test_calculate_tax_interstate():
    res = calculate_tax(taxable_amount=1000.0, gst_rate=18.0, tax_regime="INTERSTATE")
    assert res["igst"] == 180.0
    assert res["cgst"] == 0.0
    assert res["sgst"] == 0.0
    assert res["total_amount"] == 1180.0


def test_calculate_tax_intrastate():
    res = calculate_tax(taxable_amount=1000.0, gst_rate=18.0, tax_regime="INTRASTATE")
    assert res["cgst"] == 90.0
    assert res["sgst"] == 90.0
    assert res["igst"] == 0.0
    assert res["total_amount"] == 1180.0


def test_validate_tax_sample_invoice():
    extracted = {
        "supplier_gstin": "24HDE7487RE5RT4",
        "customer_gstin": "07AOLCC1206D1ZG",
        "place_of_supply": "Delhi ( 07 )",
        "taxable_amount": 3380.00,
        "gst_rate": 18.0,
        "igst": 608.40,
        "total_tax": 608.40,
        "total_amount": 3988.00
    }
    val = validate_tax(extracted)
    assert val["tax_regime"] == "INTERSTATE"
    assert val["tax_status"] == "Valid"
    assert val["regime_status"] == "Valid"
    assert val["overall_status"] == "Valid"
