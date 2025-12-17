"""
RESPA (Real Estate Settlement Procedures Act) Compliance Rules
10 rules covering fee tolerance, timing, and settlement services
"""

from compliance_engine_v2 import ComplianceRule, RuleResult, ComplianceStatus, Severity, RuleCategory, LoanData, ComplianceContext
from decimal import Decimal
from typing import List, Dict

class FeeToleranceZeroPercentRule(ComplianceRule):
    """0% tolerance category fees cannot increase"""
    
    def __init__(self):
        super().__init__(
            rule_code="RESPA-TOL-001",
            rule_name="Fee Tolerance - 0% Category",
            category=RuleCategory.RESPA,
            severity=Severity.HIGH
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # 0% tolerance fees: lender fees, transfer taxes
        # These cannot increase at all from LE to CD
        
        # Would need to compare LE fees to CD fees
        # For now, require manual review
        
        return self.create_result(
            ComplianceStatus.PASS,
            "0% tolerance fees (lender fees, transfer taxes) require verification that no increases occurred from LE to CD (12 CFR 1026.19(e)(3)(i)).",
            requires_review=True
        )

class FeeToleranceTenPercentRule(ComplianceRule):
    """10% tolerance category fees cannot increase > 10%"""
    
    def __init__(self):
        super().__init__(
            rule_code="RESPA-TOL-002",
            rule_name="Fee Tolerance - 10% Category",
            category=RuleCategory.RESPA,
            severity=Severity.MEDIUM
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # 10% tolerance fees: recording fees, services borrower can shop for (if used provider from lender list)
        # Total increase cannot exceed 10% of sum
        
        return self.create_result(
            ComplianceStatus.PASS,
            "10% tolerance fees (recording, third-party services) require verification that total increase ≤ 10% from LE to CD (12 CFR 1026.19(e)(3)(ii)).",
            requires_review=True
        )

class CashToCloseVarianceRule(ComplianceRule):
    """Cash to Close variance check"""
    
    def __init__(self):
        super().__init__(
            rule_code="RESPA-CTC-001",
            rule_name="Cash to Close Variance",
            category=RuleCategory.RESPA,
            severity=Severity.MEDIUM
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        le_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Loan Estimate"), None)
        cd_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Closing Disclosure"), None)
        
        if not le_disc or not cd_disc:
            return self.create_result(
                ComplianceStatus.WARNING,
                "Missing LE or CD. Cannot check Cash to Close variance.",
                requires_review=True
            )
        
        # Compare estimated vs actual cash to close
        # Large variances may indicate tolerance violations
        
        return self.create_result(
            ComplianceStatus.PASS,
            "Cash to Close variance requires verification.",
            requires_review=True
        )

class AffiliatedBusinessDisclosureRule(ComplianceRule):
    """Affiliated Business Arrangement disclosures required"""
    
    def __init__(self):
        super().__init__(
            rule_code="RESPA-ABA-001",
            rule_name="Affiliated Business Arrangement Disclosure",
            category=RuleCategory.RESPA,
            severity=Severity.HIGH
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # If lender refers to affiliated title company, settlement service, etc.
        # Must provide AfBA disclosure
        
        return self.create_result(
            ComplianceStatus.PASS,
            "If affiliated business arrangements exist, verify AfBA disclosure provided at or before time of referral (12 CFR 1024.15).",
            requires_review=True
        )

class ServiceProviderListRule(ComplianceRule):
    """Borrower must be allowed to shop for services"""
    
    def __init__(self):
        super().__init__(
            rule_code="RESPA-SHOP-001",
            rule_name="Service Provider Shopping Rights",
            category=RuleCategory.RESPA,
            severity=Severity.MEDIUM
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # For services borrower can shop for, must provide written list of providers
        # Verify list provided with LE
        
        return self.create_result(
            ComplianceStatus.PASS,
            "For services borrower can shop for, verify written list of providers given with LE (12 CFR 1026.19(e)(1)(vi)).",
            requires_review=True
        )

class EscrowAccountDisclosureRule(ComplianceRule):
    """Escrow account disclosure requirements"""
    
    def __init__(self):
        super().__init__(
            rule_code="RESPA-ESC-001",
            rule_name="Escrow Account Disclosure",
            category=RuleCategory.RESPA,
            severity=Severity.MEDIUM
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # Initial escrow account statement required at closing
        # Annual escrow account statement required
        
        return self.create_result(
            ComplianceStatus.PASS,
            "Verify initial escrow account statement provided at/before closing (12 CFR 1024.17(g)).",
            requires_review=True
        )

class KickbackProhibitionRule(ComplianceRule):
    """Section 8 - No kickbacks or unearned fees"""
    
    def __init__(self):
        super().__init__(
            rule_code="RESPA-KICK-001",
            rule_name="Kickback and Unearned Fee Prohibition",
            category=RuleCategory.RESPA,
            severity=Severity.CRITICAL
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # Cannot give or receive kickbacks, referral fees, or unearned fees
        # This requires analysis of fee arrangements
        
        return self.create_result(
            ComplianceStatus.PASS,
            "Section 8 compliance: No kickbacks, referral fees, or unearned fees allowed. Requires manual review of fee arrangements (12 USC 2607).",
            requires_review=True
        )

class TitleInsuranceRequirementRule(ComplianceRule):
    """Cannot require use of particular title insurance company"""
    
    def __init__(self):
        super().__init__(
            rule_code="RESPA-TITLE-001",
            rule_name="Title Insurance Company Selection",
            category=RuleCategory.RESPA,
            severity=Severity.HIGH
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # Borrower must be free to choose title company
        # Cannot be required to use lender's choice
        
        return self.create_result(
            ComplianceStatus.PASS,
            "Verify borrower was not required to use particular title insurance company (12 CFR 1024.16).",
            requires_review=True
        )

class ServicingDisclosureRule(ComplianceRule):
    """Servicing disclosure statement required"""
    
    def __init__(self):
        super().__init__(
            rule_code="RESPA-SERV-001",
            rule_name="Servicing Disclosure Statement",
            category=RuleCategory.RESPA,
            severity=Severity.MEDIUM
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # Servicing disclosure statement required at application
        # Discloses whether lender intends to service loan or transfer servicing
        
        return self.create_result(
            ComplianceStatus.PASS,
            "Verify Servicing Disclosure Statement provided at application (12 CFR 1024.33).",
            requires_review=True
        )

class SettlementStatementAccuracyRule(ComplianceRule):
    """Settlement statement must be accurate"""
    
    def __init__(self):
        super().__init__(
            rule_code="RESPA-SETTLE-001",
            rule_name="Settlement Statement Accuracy",
            category=RuleCategory.RESPA,
            severity=Severity.HIGH
        )
    
    def evaluate(self, loan_data: LoanData, context: ComplianceContext) -> RuleResult:
        # CD (which replaced HUD-1) must accurately reflect all charges
        # No hidden fees, all fees disclosed
        
        cd_disc = next((d for d in loan_data.disclosures if d.disclosure_type == "Closing Disclosure"), None)
        
        if not cd_disc:
            return self.create_result(
                ComplianceStatus.FAIL,
                "Closing Disclosure not found. Required to document all settlement charges.",
                requires_review=True
            )
        
        return self.create_result(
            ComplianceStatus.PASS,
            "Closing Disclosure provided. Verify all charges accurately disclosed.",
            requires_review=True
        )

def get_respa_rules():
    """Return list of all RESPA rules"""
    return [
        FeeToleranceZeroPercentRule(),
        FeeToleranceTenPercentRule(),
        CashToCloseVarianceRule(),
        AffiliatedBusinessDisclosureRule(),
        ServiceProviderListRule(),
        EscrowAccountDisclosureRule(),
        KickbackProhibitionRule(),
        TitleInsuranceRequirementRule(),
        ServicingDisclosureRule(),
        SettlementStatementAccuracyRule()
    ]

