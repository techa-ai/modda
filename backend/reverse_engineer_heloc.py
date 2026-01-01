import sys
from bedrock_config import call_bedrock

def reverse_engineer_calculation():
    print("🤖 Asking Claude Opus to reverse engineer $2,744.22...")
    
    prompt = """
You are a Mortgage Mathematics Expert.
A Loan Attribute "Proposed Monthly Second Mortgage P&I" has a value of **$2,744.22**.
We need to find the formula used to derive this number.

KNOWN VARIABLES (from HELOC Agreement):
- Loan Type: HELOC (Home Equity Line of Credit) / Second Mortgage
- Credit Limit / Balance: $300,000.00
- Initial Advance: $300,000.00
- Initial Interest Rate: 8.500%
- Term: 30 Years (360 Months) total
- Structure: Draw Period + Repayment Period (possibly 10/20 split?)
- Lien Position: 2nd

TARGET VALUE: $2,744.22

TASK:
Try various mortgage calculation methods to match the target value exactly (or within pennies).
Consider:
1. Interest Only Payment
2. Amortized Payment (Full 30 Year Term)
3. Amortized Payment (20 Year Repayment Term)
4. Amortized Payment (Any other term, e.g. 18 years, 25 years?)
5. Percentage of Balance (e.g. 1%, 1.5%, 1.25%, 0.xxx%)
6. Rate stress testing (e.g. Rate + 2%?)
7. 360 vs 365 day year interest?

OUTPUT:
Explain the calculation that matches $2,744.22. If no standard calculation matches, explain the closest one and the discrepancy.
"""

    response = call_bedrock(prompt, model='claude-opus-4-5', max_tokens=2000)
    print("\n💡 CLAUDE'S ANALYSIS:\n")
    print(response)

if __name__ == "__main__":
    reverse_engineer_calculation()



