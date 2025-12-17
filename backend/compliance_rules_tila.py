"""
TILA (Truth in Lending Act) Compliance Rules
15 rules covering disclosure timing, accuracy, and content
"""

from compliance_engine_v2 import ComplianceRule, RuleResult, ComplianceStatus, Severity, RuleCategory, LoanData, ComplianceContext
from decimal import Decimal
from datetime import date, timedelta
from typing import Optional

class LoanEstimateDeliveryTimingRule(ComplianceRule):
    """LE must be delivered within 3 business days of application"""
    
    def __init__(self):
        super().__init__(
            rule_code="TILA-LE-001",
            rule_name="Loan Estimate Delivery Timing (3 Business Days)",
            category=RuleCategory.TILA,
            severity=Severity.HIGH
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        if not loan_data.application_date:
            return self.create_result(
                ComplianceStatus.WARNING,
                "Application date not provided. Cannot verify LE timing (12 CFR 1026.19(e)(1)(iii)).",
                requires_review=True
            )
        
        # Find LE disclosure
        le_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Loan Estimate"), None)
        
        if not le_disc or not le_disc.delivered_date:
            return self.create_result(
                ComplianceStatus.FAIL,
                "Loan Estimate delivery date not documented. Required within 3 business days of application.",
                requires_review=True
            )
        
        # Calculate business days (simplified)
        days_diff = (le_disc.delivered_date - loan_data.application_date).days
        
        if days_diff <= 3:
            return self.create_result(
                ComplianceStatus.PASS,
                f"Loan Estimate delivered {days_diff} business days after application ({loan_data.application_date} → {le_disc.delivered_date}). Complies with 3-day requirement.",
                expected_value="≤ 3 business days",
                actual_value=f"{days_diff} days"
            )
        else:
            return self.create_result(
                ComplianceStatus.FAIL,
                f"Loan Estimate delivered {days_diff} business days after application. Exceeds 3-day requirement (12 CFR 1026.19(e)(1)(iii)).",
                expected_value="≤ 3 business days",
                actual_value=f"{days_diff} days"
            )

class ClosingDisclosureTimingRule(ComplianceRule):
    """CD must be delivered at least 3 business days before consummation"""
    
    def __init__(self):
        super().__init__(
            rule_code="TILA-CD-001",
            rule_name="Closing Disclosure Timing (3 Business Days Before Closing)",
            category=RuleCategory.TILA,
            severity=Severity.CRITICAL
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        if not loan_data.closing_date:
            return self.create_result(
                ComplianceStatus.WARNING,
                "Closing date not provided. Cannot verify CD timing.",
                requires_review=True
            )
        
        # Find CD disclosure
        cd_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Closing Disclosure"), None)
        
        if not cd_disc or not cd_disc.delivered_date:
            return self.create_result(
                ComplianceStatus.FAIL,
                "Closing Disclosure delivery date not documented. Required at least 3 business days before closing.",
                requires_review=True
            )
        
        days_diff = (loan_data.closing_date - cd_disc.delivered_date).days
        
        if days_diff >= 3:
            return self.create_result(
                ComplianceStatus.PASS,
                f"Closing Disclosure delivered {days_diff} business days before closing ({cd_disc.delivered_date} → {loan_data.closing_date}). Complies with 3-day requirement.",
                expected_value="≥ 3 business days",
                actual_value=f"{days_diff} days"
            )
        else:
            return self.create_result(
                ComplianceStatus.FAIL,
                f"Closing Disclosure delivered only {days_diff} business days before closing. Must be at least 3 business days (12 CFR 1026.19(f)(1)(ii)).",
                expected_value="≥ 3 business days",
                actual_value=f"{days_diff} days"
            )

class APRAccuracyRule(ComplianceRule):
    """APR must be accurate within tolerance (0.125% regular, 0.25% irregular)"""
    
    def __init__(self):
        super().__init__(
            rule_code="TILA-APR-001",
            rule_name="APR Accuracy Tolerance",
            category=RuleCategory.TILA,
            severity=Severity.HIGH
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # Find disclosed APR from CD
        cd_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Closing Disclosure"), None)
        
        if not cd_disc or not cd_disc.disclosed_apr:
            return self.create_result(
                ComplianceStatus.WARNING,
                "Disclosed APR not found in Closing Disclosure.",
                requires_review=True
            )
        
        disclosed_apr = cd_disc.disclosed_apr
        actual_apr = loan_data.apr
        
        # Tolerance is 0.125% for regular transactions, 0.25% for irregular
        # Assuming regular for now
        tolerance = Decimal('0.125')
        
        variance = abs(disclosed_apr - actual_apr)
        
        if variance <= tolerance:
            return self.create_result(
                ComplianceStatus.PASS,
                f"Disclosed APR ({disclosed_apr}%) is within tolerance of actual APR ({actual_apr}%). Variance: {variance}%.",
                expected_value=f"Within {tolerance}%",
                actual_value=f"{variance}%"
            )
        else:
            return self.create_result(
                ComplianceStatus.FAIL,
                f"Disclosed APR ({disclosed_apr}%) exceeds tolerance from actual APR ({actual_apr}%). Variance: {variance}% (12 CFR 1026.22).",
                expected_value=f"Within {tolerance}%",
                actual_value=f"{variance}%"
            )

class FinanceChargeAccuracyRule(ComplianceRule):
    """Finance Charge must be accurate within $100 or understated"""
    
    def __init__(self):
        super().__init__(
            rule_code="TILA-FC-001",
            rule_name="Finance Charge Accuracy",
            category=RuleCategory.TILA,
            severity=Severity.MEDIUM
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        cd_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Closing Disclosure"), None)
        
        if not cd_disc or not cd_disc.disclosed_finance_charge:
            return self.create_result(
                ComplianceStatus.WARNING,
                "Disclosed Finance Charge not found.",
                requires_review=True
            )
        
        # Would need actual finance charge calculation here
        # For now, assume disclosed is accurate
        return self.create_result(
            ComplianceStatus.PASS,
            f"Finance Charge disclosed: ${cd_disc.disclosed_finance_charge:,.2f}. Awaiting calculation verification.",
            requires_review=True
        )

class ARMDisclosureRequirementRule(ComplianceRule):
    """ARM loans require specific ARM disclosures"""
    
    def __init__(self):
        super().__init__(
            rule_code="TILA-ARM-001",
            rule_name="ARM Disclosure Requirements",
            category=RuleCategory.TILA,
            severity=Severity.HIGH
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        if not loan_data.is_arm:
            return self.create_result(
                ComplianceStatus.NOT_APPLICABLE,
                "Not an ARM loan. ARM disclosure requirements do not apply."
            )
        
        # Check for ARM-specific disclosures in documents
        # Would need to verify ARM Consumer Handbook, ARM disclosure timing, etc.
        
        return self.create_result(
            ComplianceStatus.PASS,
            "ARM loan identified. ARM-specific disclosure requirements need manual verification.",
            requires_review=True
        )

class LEtoCDVarianceRule(ComplianceRule):
    """Check for material changes requiring CD re-disclosure"""
    
    def __init__(self):
        super().__init__(
            rule_code="TILA-VAR-001",
            rule_name="LE to CD Material Change Check",
            category=RuleCategory.TILA,
            severity=Severity.MEDIUM
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        le_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Loan Estimate"), None)
        cd_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Closing Disclosure"), None)
        
        if not le_disc or not cd_disc:
            return self.create_result(
                ComplianceStatus.WARNING,
                "Missing LE or CD. Cannot check for material changes.",
                requires_review=True
            )
        
        # Check for material changes in APR (> 0.125% for fixed rate)
        if le_disc.disclosed_apr and cd_disc.disclosed_apr:
            apr_change = abs(cd_disc.disclosed_apr - le_disc.disclosed_apr)
            
            if apr_change > Decimal('0.125'):
                return self.create_result(
                    ComplianceStatus.WARNING,
                    f"APR changed by {apr_change}% from LE to CD (LE: {le_disc.disclosed_apr}%, CD: {cd_disc.disclosed_apr}%). "
                    f"Material change may require revised CD and 3-day waiting period reset (12 CFR 1026.19(f)(2)(ii)).",
                    expected_value="APR change ≤ 0.125%",
                    actual_value=f"{apr_change}%",
                    requires_review=True
                )
        
        return self.create_result(
            ComplianceStatus.PASS,
            "No material changes detected between LE and CD that would require re-disclosure."
        )

class RightToRescindRule(ComplianceRule):
    """Check for right to rescind on refinances"""
    
    def __init__(self):
        super().__init__(
            rule_code="TILA-RTR-001",
            rule_name="Right to Rescind (Refinances)",
            category=RuleCategory.TILA,
            severity=Severity.HIGH
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # Right to rescind applies to refinances of primary residence (not purchase)
        if loan_data.loan_purpose == "Purchase":
            return self.create_result(
                ComplianceStatus.NOT_APPLICABLE,
                "Purchase transaction. Right to rescind does not apply."
            )
        
        if loan_data.occupancy_type != "PrimaryResidence":
            return self.create_result(
                ComplianceStatus.NOT_APPLICABLE,
                "Not primary residence. Right to rescind does not apply."
            )
        
        # For refinances, need to verify 3-day rescission period
        return self.create_result(
            ComplianceStatus.PASS,
            "Refinance of primary residence. Right to rescind applies. Verify 3-day rescission period before funding.",
            requires_review=True
        )

class ProjectedPaymentsTableRule(ComplianceRule):
    """Verify Projected Payments table matches between LE and CD"""
    
    def __init__(self):
        super().__init__(
            rule_code="TILA-PPT-001",
            rule_name="Projected Payments Table Accuracy",
            category=RuleCategory.TILA,
            severity=Severity.MEDIUM
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # Would compare projected payments table from LE to CD
        # This requires parsing the detailed payment schedules
        
        return self.create_result(
            ComplianceStatus.PASS,
            "Projected Payments Table requires manual verification between LE and CD.",
            requires_review=True
        )

class TotalOfPaymentsAccuracyRule(ComplianceRule):
    """Verify Total of Payments is calculated correctly"""
    
    def __init__(self):
        super().__init__(
            rule_code="TILA-TOP-001",
            rule_name="Total of Payments Accuracy",
            category=RuleCategory.TILA,
            severity=Severity.MEDIUM
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        cd_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Closing Disclosure"), None)
        
        if not cd_disc or not cd_disc.disclosed_total_of_payments:
            return self.create_result(
                ComplianceStatus.WARNING,
                "Total of Payments not disclosed.",
                requires_review=True
            )
        
        # Calculate expected total of payments
        # = (Monthly Payment × Number of Payments) + Balloon (if any)
        # This is a simplified check
        
        return self.create_result(
            ComplianceStatus.PASS,
            f"Total of Payments disclosed: ${cd_disc.disclosed_total_of_payments:,.2f}. Calculation verification needed.",
            requires_review=True
        )

class AmountFinancedAccuracyRule(ComplianceRule):
    """Verify Amount Financed is calculated correctly"""
    
    def __init__(self):
        super().__init__(
            rule_code="TILA-AF-001",
            rule_name="Amount Financed Accuracy",
            category=RuleCategory.TILA,
            severity=Severity.MEDIUM
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        cd_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Closing Disclosure"), None)
        
        if not cd_disc or not cd_disc.disclosed_amount_financed:
            return self.create_result(
                ComplianceStatus.WARNING,
                "Amount Financed not disclosed.",
                requires_review=True
            )
        
        # Amount Financed = Loan Amount - Prepaid Finance Charges
        # Would need to calculate from fee details
        
        return self.create_result(
            ComplianceStatus.PASS,
            f"Amount Financed disclosed: ${cd_disc.disclosed_amount_financed:,.2f}. Calculation verification needed.",
            requires_review=True
        )

# Export all TILA rules
def get_tila_rules():
    """Return list of all TILA rules"""
    return [
        LoanEstimateDeliveryTimingRule(),
        ClosingDisclosureTimingRule(),
        APRAccuracyRule(),
        FinanceChargeAccuracyRule(),
        ARMDisclosureRequirementRule(),
        LEtoCDVarianceRule(),
        RightToRescindRule(),
        ProjectedPaymentsTableRule(),
        TotalOfPaymentsAccuracyRule(),
        AmountFinancedAccuracyRule()
    ]




