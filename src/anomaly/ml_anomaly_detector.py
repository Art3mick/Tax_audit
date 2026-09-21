import numpy as np
from typing import Dict, Any, List
from sklearn.ensemble import IsolationForest


class GSTIsolationForestDetector:
    """
    Unsupervised Isolation Forest Anomaly Detector tailored for Indian GST Invoices.
    Identifies statistical price anomalies, unusual tax-to-taxable ratios,
    and suspicious threshold proximity (e.g. splitting invoices near ₹50,000 E-Way bill threshold).
    """

    def __init__(self, contamination: float = 0.05):
        self.contamination = contamination
        self.model = IsolationForest(
            n_estimators=100,
            contamination=self.contamination,
            random_state=42
        )
        self.is_trained = False

    def extract_features(self, fields: Dict[str, Any]) -> np.ndarray:
        """
        Converts extracted invoice fields into a 7-dimensional feature vector:
        1. Taxable Amount (₹)
        2. Total Tax Amount (₹)
        3. Grand Total Amount (₹)
        4. Effective GST Rate (%)
        5. Tax-to-Taxable Ratio
        6. Proximity to ₹50,000 E-Way Bill Threshold (|Total - 50000|)
        7. Line Item Count
        """
        taxable = float(fields.get("taxable_amount") or 0.0)
        total_tax = float(fields.get("total_tax") or 0.0)
        total_amount = float(fields.get("total_amount") or (taxable + total_tax))
        gst_rate = float(fields.get("gst_rate") or 18.0)

        tax_ratio = (total_tax / taxable) if taxable > 0 else 0.0
        eway_proximity = abs(total_amount - 50000.0)
        num_items = float(len(fields.get("items", []) or []))

        return np.array([
            taxable,
            total_tax,
            total_amount,
            gst_rate,
            tax_ratio,
            eway_proximity,
            num_items
        ], dtype=float)

    def train_on_records(self, records: List[Dict[str, Any]]) -> bool:
        """
        Trains or fits the Isolation Forest on a batch of invoice record dictionaries.
        Needs at least 5 records to train.
        """
        if len(records) < 5:
            return False

        feature_matrix = np.array([self.extract_features(r) for r in records])
        self.model.fit(feature_matrix)
        self.is_trained = True
        return True

    def train_synthetic_fallback(self):
        """
        Generates a synthetic baseline dataset representing typical Indian small business purchase invoices
        (GST rates: 5%, 12%, 18%, 28%) to pre-train the model if local DB history is small.
        """
        np.random.seed(42)
        n_samples = 300
        synthetic_records = []

        gst_rates = [5.0, 12.0, 18.0, 28.0]
        for _ in range(n_samples):
            rate = np.random.choice(gst_rates, p=[0.3, 0.25, 0.35, 0.1])
            taxable = float(np.random.uniform(500, 75000))
            total_tax = round(taxable * (rate / 100.0), 2)
            grand_total = round(taxable + total_tax, 2)
            num_items = int(np.random.randint(1, 8))

            synthetic_records.append({
                "taxable_amount": taxable,
                "total_tax": total_tax,
                "total_amount": grand_total,
                "gst_rate": rate,
                "items": [1] * num_items
            })

        self.train_on_records(synthetic_records)

    def predict(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates a target invoice dictionary and returns ML anomaly metrics.
        Returns:
            - is_anomaly (bool)
            - ml_score (float 0-100, where higher means more anomalous)
            - rationale (str)
        """
        if not self.is_trained:
            self.train_synthetic_fallback()

        vector = self.extract_features(fields).reshape(1, -1)
        pred = self.model.predict(vector)[0]  # 1 = Normal, -1 = Anomaly
        raw_score = float(self.model.score_samples(vector)[0])

        # Normalize Isolation Forest score (-0.8 to 0.2 approx -> 0 to 100 risk score)
        anomaly_score = round(max(0.0, min(100.0, (0.2 - raw_score) * 100)), 1)
        is_anomaly = (pred == -1) and (anomaly_score >= 65.0)

        rationale = (
            f"🤖 [ML Anomaly Alert] Statistical outlier detected (Isolation Forest Score: {anomaly_score}/100). "
            "This invoice differs significantly from typical purchase transaction patterns."
            if is_anomaly else
            f"🤖 [ML Verification] Transaction fits standard statistical invoice patterns (iForest Score: {anomaly_score}/100)."
        )

        return {
            "is_anomaly": is_anomaly,
            "ml_anomaly_score": anomaly_score,
            "ml_decision": "Anomalous" if is_anomaly else "Normal",
            "ml_rationale": rationale
        }
