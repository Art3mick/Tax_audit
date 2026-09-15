import re
from typing import Dict, Any, Optional

# Indian State GST Code Mapping (01 to 38)
GST_STATE_CODES: Dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (Old)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh (New)",
    "38": "Ladakh"
}


def get_state_from_gstin(gstin: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Extracts state code and state name from 15-character Indian GSTIN.
    """
    if not gstin or len(gstin) < 2:
        return None
    code = gstin[:2]
    if code in GST_STATE_CODES:
        return {"code": code, "state_name": GST_STATE_CODES[code]}
    return None


def validate_gstin_format(gstin: Optional[str]) -> Dict[str, Any]:
    """
    Validates GSTIN structure: 2 digits (state), 5 letters (PAN), 4 digits, 1 letter, 1 char, 'Z', 1 char.
    """
    if not gstin:
        return {"valid": False, "reason": "GSTIN missing"}
    
    gstin = gstin.upper().strip()
    pattern = r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z0-9]{1}Z[A-Z0-9]{1}$"
    
    if not re.match(pattern, gstin):
        return {"valid": False, "reason": "Invalid GSTIN format structure"}
        
    state_info = get_state_from_gstin(gstin)
    if not state_info:
        return {"valid": False, "reason": "Invalid state code in GSTIN"}
        
    return {"valid": True, "state_code": state_info["code"], "state_name": state_info["state_name"]}


def determine_tax_regime(
    supplier_gstin: Optional[str],
    customer_gstin: Optional[str],
    place_of_supply: Optional[str] = None
) -> str:
    """
    Determines whether a transaction is INTERSTATE (IGST) or INTRASTATE (CGST+SGST).
    If Supplier State != Customer State / Place of Supply State -> INTERSTATE.
    """
    supplier_state = get_state_from_gstin(supplier_gstin)
    customer_state = get_state_from_gstin(customer_gstin)
    
    sup_code = supplier_state["code"] if supplier_state else None
    cust_code = customer_state["code"] if customer_state else None

    # Check Place of Supply code if present (e.g. "Delhi ( 07 )")
    pos_code = None
    if place_of_supply:
        pos_match = re.search(r"\(?\b(\d{2})\b\)?", place_of_supply)
        if pos_match:
            pos_code = pos_match.group(1)

    target_code = cust_code or pos_code
    
    if sup_code and target_code:
        if sup_code != target_code:
            return "INTERSTATE"
        else:
            return "INTRASTATE"
            
    return "INTRASTATE"  # Default assumption if state codes unknown


def calculate_tax(
    taxable_amount: float,
    gst_rate: float,
    tax_regime: str = "INTRASTATE"
) -> Dict[str, Any]:
    """
    Calculates expected GST amounts based on taxable amount, rate %, and tax regime.
    """
    taxable_amount = float(taxable_amount)
    gst_rate = float(gst_rate)
    total_tax = taxable_amount * (gst_rate / 100.0)

    if tax_regime == "INTERSTATE":
        igst = total_tax
        cgst = 0.0
        sgst = 0.0
    else:
        igst = 0.0
        cgst = total_tax / 2.0
        sgst = total_tax / 2.0

    total_amount = taxable_amount + total_tax

    return {
        "taxable_amount": round(taxable_amount, 2),
        "gst_rate": gst_rate,
        "tax_regime": tax_regime,
        "cgst": round(cgst, 2),
        "sgst": round(sgst, 2),
        "igst": round(igst, 2),
        "total_tax": round(total_tax, 2),
        "total_amount": round(total_amount, 2)
    }


def validate_tax(extracted_fields: Dict[str, Any], tolerance: float = 2.0) -> Dict[str, Any]:
    """
    Comprehensive GST tax validation:
    1. Determines state codes and tax regime (INTERSTATE vs INTRASTATE).
    2. Compares extracted vs calculated tax values.
    3. Checks for tax regime mismatches (e.g. charging CGST/SGST on Interstate transaction).
    4. Checks rounding tolerance.
    """
    taxable = extracted_fields.get("taxable_amount")
    gst_rate = extracted_fields.get("gst_rate") or 18.0
    stated_cgst = extracted_fields.get("cgst")
    stated_sgst = extracted_fields.get("sgst")
    stated_igst = extracted_fields.get("igst")
    stated_tax = extracted_fields.get("total_tax")
    stated_total = extracted_fields.get("total_amount")
    
    supplier_gstin = extracted_fields.get("supplier_gstin")
    customer_gstin = extracted_fields.get("customer_gstin")
    place_of_supply = extracted_fields.get("place_of_supply")

    # Determine Tax Regime
    regime = determine_tax_regime(supplier_gstin, customer_gstin, place_of_supply)

    validation_result: Dict[str, Any] = {
        "tax_regime": regime,
        "supplier_state": get_state_from_gstin(supplier_gstin),
        "customer_state": get_state_from_gstin(customer_gstin),
        "calculated_values": None,
        "discrepancies": [],
        "tax_status": "Valid",
        "regime_status": "Valid",
        "overall_status": "Valid"
    }

    if taxable is None:
        validation_result["overall_status"] = "Needs Review"
        validation_result["discrepancies"].append("Taxable amount missing or not extracted.")
        return validation_result

    # Calculate expected tax values
    calculated = calculate_tax(taxable, gst_rate, regime)
    validation_result["calculated_values"] = calculated

    # Regime check: check if IGST charged when Intrastate OR CGST/SGST charged when Interstate
    if regime == "INTERSTATE":
        if (stated_cgst and stated_cgst > 0) or (stated_sgst and stated_sgst > 0):
            validation_result["regime_status"] = "Mismatch"
            validation_result["discrepancies"].append(
                "Tax Regime Error: CGST/SGST charged on Inter-state transaction (Supplier and Buyer/Place of Supply in different states). IGST should be charged."
            )
    elif regime == "INTRASTATE":
        if stated_igst and stated_igst > 0:
            validation_result["regime_status"] = "Mismatch"
            validation_result["discrepancies"].append(
                "Tax Regime Error: IGST charged on Intra-state transaction (Supplier and Buyer in same state). CGST+SGST should be charged."
            )

    # Tax math check
    if stated_tax is not None:
        tax_diff = abs(calculated["total_tax"] - stated_tax)
        if tax_diff > tolerance:
            validation_result["tax_status"] = "Mismatch"
            validation_result["discrepancies"].append(
                f"Tax Amount Difference: Stated Total Tax (₹{stated_tax:.2f}) differs from Calculated Tax (₹{calculated['total_tax']:.2f}) by ₹{tax_diff:.2f}."
            )

    # Total amount math check
    if stated_total is not None:
        total_diff = abs(calculated["total_amount"] - stated_total)
        if total_diff > tolerance:
            validation_result["tax_status"] = "Mismatch"
            validation_result["discrepancies"].append(
                f"Grand Total Difference: Stated Grand Total (₹{stated_total:.2f}) differs from Calculated Total (₹{calculated['total_amount']:.2f}) by ₹{total_diff:.2f}."
            )

    if validation_result["discrepancies"]:
        validation_result["overall_status"] = "Needs Review"

    return validation_result