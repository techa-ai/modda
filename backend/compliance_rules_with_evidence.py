"""
Enhanced Compliance Rules with Evidence Tracking
Updates existing rules to capture detailed evidence for audit trails
"""

from compliance_engine_v2 import *
from compliance_evidence import ComplianceEvidence

class QMPointsAndFeesRuleEnhanced(ComplianceRule):
    """QM Points and Fees Limit - WITH EVIDENCE TRACKING"""
    
    def __init__(self):
        super().__init__(
            rule_code="QM-FEES-001",
            rule_name="QM Points and Fees Limit",
            category=RuleCategory.ATR_QM,
            severity=Severity.HIGH
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # Create evidence object
        evidence = ComplianceEvidence()
        
        # Calculate fees
        total_fees, percentage = PointsAndFeesCalculator.calculate_qm_points_and_fees(loan_data)
        limit = PointsAndFeesCalculator.get_qm_points_fees_limit(loan_data.loan_amount)
        
        # Store in context
        context.qm_points_fees_amount = total_fees
        context.qm_points_fees_pct = percentage
        
        # Track evidence - Documents used (generic references since we don't have individual fees)
        evidence.add_document(
            doc_id=f"CD_{loan_data.loan_id}",
            doc_type="CLOSING_DISCLOSURE",
            doc_name="Closing Disclosure.pdf",
            page=2,
            section="Loan Costs - Origination Charges",
            field_location="Section A + Applicable Section B, C Fees"
        )
        
        evidence.add_document(
            doc_id=f"LE_{loan_data.loan_id}",
            doc_type="LOAN_ESTIMATE",
            doc_name="Loan Estimate.pdf",
            page=1,
            section="Loan Terms",
            field_location="Loan Amount"
        )
        
        # Track extracted values
        evidence.add_value(
            field_name="Total Loan Amount",
            value=float(loan_data.loan_amount),
            unit="USD",
            source_doc_id=f"LE_{loan_data.loan_id}",
            source_page=1,
            source_field="Loan Terms - Loan Amount"
        )
        
        evidence.add_value(
            field_name="Total QM Points & Fees",
            value=float(total_fees),
            unit="USD",
            source_doc_id=f"CD_{loan_data.loan_id}",
            source_page=2,
            source_field="Origination Charges + Applicable Fees"
        )
        
        # Track calculation
        evidence.add_calculation(
            calc_name="QM Points & Fees Percentage",
            formula="(Total QM Fees / Loan Amount) × 100",
            inputs=[
                {"variable": "Total QM Fees", "value": float(total_fees), "unit": "USD"},
                {"variable": "Loan Amount", "value": float(loan_data.loan_amount), "unit": "USD"}
            ],
            result=float(percentage),
            result_unit="PERCENT",
            threshold_operator="<=",
            threshold_value=float(limit),
            threshold_met=(percentage <= limit)
        )
        
        # Set rationale based on result
        if percentage <= limit:
            evidence.set_rationale(
                summary=f"QM Points & Fees percentage ({percentage:.3f}%) is within the regulatory limit ({limit}%).",
                key_findings=[
                    f"Total QM fees: ${total_fees:,.2f}",
                    f"Loan amount: ${loan_data.loan_amount:,.2f}",
                    f"Percentage: {percentage:.3f}%",
                    f"Limit: {limit}%",
                    f"Under by: {limit - percentage:.3f} percentage points"
                ],
                conclusion="PASS - Loan qualifies for QM status based on points & fees test.",
                regulatory_reference="12 CFR 1026.43(e)(3) - QM Points and Fees Limit"
            )
            
            result = self.create_result(
                ComplianceStatus.PASS,
                f"QM Points & Fees ({percentage:.3f}%) within limit ({limit}%). Total fees: ${total_fees:,.2f}",
                expected_value=f"<= {limit}%",
                actual_value=f"{percentage:.3f}%"
            )
        else:
            excess = percentage - limit
            evidence.set_rationale(
                summary=f"QM Points & Fees percentage ({percentage:.3f}%) EXCEEDS the regulatory limit ({limit}%).",
                key_findings=[
                    f"Total QM fees: ${total_fees:,.2f}",
                    f"Loan amount: ${loan_data.loan_amount:,.2f}",
                    f"Percentage: {percentage:.3f}%",
                    f"Limit: {limit}%",
                    f"Excess: {excess:.3f} percentage points"
                ],
                conclusion="FAIL - Loan does NOT qualify for QM status. Fees must be reduced or loan restructured.",
                risk_notes=[
                    "Loan cannot be sold as QM to GSEs",
                    "Higher risk retention requirements",
                    "May face regulatory scrutiny"
                ],
                regulatory_reference="12 CFR 1026.43(e)(3) - QM Points and Fees Limit"
            )
            
            result = self.create_result(
                ComplianceStatus.FAIL,
                f"QM Points & Fees ({percentage:.3f}%) exceeds limit ({limit}%). Total fees: ${total_fees:,.2f}",
                expected_value=f"<= {limit}%",
                actual_value=f"{percentage:.3f}%"
            )
        
        # Attach evidence to result
        result.evidence = evidence.to_dict()
        
        return result


class QMPriceBasedLimitRuleEnhanced(ComplianceRule):
    """General QM Price-Based Limit (First Lien) - WITH EVIDENCE"""
    
    def __init__(self, reference_data=None):
        super().__init__(
            rule_code="QM-PRICE-001",
            rule_name="General QM Price-Based Limit (First Lien)",
            category=RuleCategory.ATR_QM,
            severity=Severity.HIGH
        )
        self.reference_data = reference_data
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        evidence = ComplianceEvidence()
        
        # Get APOR and calculate spread
        apor_rate = ReferenceDataProvider.get_apor_rate(loan_data.loan_type, loan_data.lock_date)
        if not apor_rate:
            result = self.create_result(
                ComplianceStatus.PENDING_REVIEW,
                f"APOR rate not available for {loan_data.lock_date}",
                requires_manual_review=True
            )
            result.evidence = evidence.to_dict()
            return result
        
        apor_spread = APORSpreadCalculator.calculate_apor_spread(loan_data.apr, apor_rate)
        
        # Store in context
        context.apor_rate = apor_rate
        context.apor_spread = apor_spread
        
        # Determine threshold
        qm_threshold = Decimal("2.25")  # First lien threshold
        
        # Add evidence - Documents
        evidence.add_document(
            doc_id=f"CD_{loan_data.loan_id}",
            doc_type="CLOSING_DISCLOSURE",
            doc_name="Closing Disclosure.pdf",
            page=5,
            section="Comparisons",
            field_location="Annual Percentage Rate (APR)"
        )
        
        evidence.add_document(
            doc_id=f"APOR_{loan_data.lock_date}",
            doc_type="REFERENCE_DATA",
            doc_name="APOR Rate Table",
            page=1,
            section=f"Rate Lock Date: {loan_data.lock_date}"
        )
        
        # Add extracted values
        evidence.add_value(
            field_name="Loan APR",
            value=float(loan_data.apr),
            unit="PERCENT",
            source_doc_id=f"CD_{loan_data.loan_id}",
            source_page=5,
            source_field="Annual Percentage Rate"
        )
        
        evidence.add_value(
            field_name="Comparable APOR",
            value=float(apor_rate),
            unit="PERCENT",
            source_doc_id=f"APOR_{loan_data.lock_date}",
            source_page=1,
            source_field=f"{loan_data.loan_type.value} Rate"
        )
        
        # Add calculation
        evidence.add_calculation(
            calc_name="APOR Spread",
            formula="Loan APR - Comparable APOR",
            inputs=[
                {"variable": "Loan APR", "value": float(loan_data.apr), "unit": "PERCENT"},
                {"variable": "APOR", "value": float(apor_rate), "unit": "PERCENT"}
            ],
            result=float(apor_spread),
            result_unit="PERCENT",
            threshold_operator="<",
            threshold_value=float(qm_threshold),
            threshold_met=(apor_spread < qm_threshold)
        )
        
        # Evaluate
        if apor_spread < qm_threshold:
            evidence.set_rationale(
                summary=f"APR ({loan_data.apr}%) does not exceed QM price threshold (APOR {apor_rate}% + {qm_threshold}%).",
                key_findings=[
                    f"Loan APR: {loan_data.apr}%",
                    f"Comparable APOR: {apor_rate}%",
                    f"APOR Spread: {apor_spread}%",
                    f"QM Threshold: {qm_threshold}% above APOR",
                    f"Spread is {qm_threshold - apor_spread:.2f}% below threshold"
                ],
                conclusion="PASS - Loan qualifies for General QM status based on pricing.",
                regulatory_reference="12 CFR 1026.43(e)(2)(vi) - General QM APR Limit"
            )
            
            result = self.create_result(
                ComplianceStatus.PASS,
                f"APR ({loan_data.apr}%) does not exceed QM price threshold ({qm_threshold}%), "
                f"which is the comparable APOR ({apor_rate}%) plus {qm_threshold}.",
                expected_value=f"< {qm_threshold}%",
                actual_value=f"{apor_spread}%"
            )
        else:
            excess = apor_spread - qm_threshold
            evidence.set_rationale(
                summary=f"APR ({loan_data.apr}%) EXCEEDS QM price threshold (APOR {apor_rate}% + {qm_threshold}%).",
                key_findings=[
                    f"Loan APR: {loan_data.apr}%",
                    f"Comparable APOR: {apor_rate}%",
                    f"APOR Spread: {apor_spread}%",
                    f"QM Threshold: {qm_threshold}% above APOR",
                    f"Exceeds threshold by: {excess:.2f}%"
                ],
                conclusion="FAIL - Loan does NOT qualify for General QM status. Consider Seasoned QM or restructure.",
                risk_notes=[
                    "Loan is priced too high for General QM",
                    "May still qualify as Seasoned QM after 36 months",
                    "Non-QM loans have higher risk retention requirements"
                ],
                regulatory_reference="12 CFR 1026.43(e)(2)(vi) - General QM APR Limit"
            )
            
            result = self.create_result(
                ComplianceStatus.FAIL,
                f"APR ({loan_data.apr}%) exceeds QM price threshold ({qm_threshold}%). "
                f"Spread over APOR ({apor_rate}%) is {apor_spread}%.",
                expected_value=f"< {qm_threshold}%",
                actual_value=f"{apor_spread}%"
            )
        
        result.evidence = evidence.to_dict()
        return result


# Helper to retrofit evidence into existing rules
def add_evidence_to_result(result: RuleResult, evidence: ComplianceEvidence) -> RuleResult:
    """Helper function to add evidence to any rule result"""
    result.evidence = evidence.to_dict()
    return result

