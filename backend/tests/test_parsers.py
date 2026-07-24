"""
Test parsers - using verified working formats
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.parsers import parse_email

# =============================================
# STERLING BANK - Verified working format
# =============================================
STERLING_DEBIT = """
Date: 30/04/2026 7:24 AM
Account Number: *****12345
Description: Data purchase for 08012345678
Amount: NGN1,605.00
Transaction: DEBIT
"""

STERLING_CREDIT = """
Date: 01/03/2026 8:58 AM
Account Number: *****12345
Description: Transfer from JOHN DOE
Amount: NGN25,000.00
Transaction: CREDIT
"""

# =============================================
# WEMA/ALAT - Complete format
# =============================================
WEMA_DEBIT = """
Transaction Notification
Hi Customer,
NGN 2,450.00 has left your ALAT Account.

Here is what you need to know:
Reference No: REF123456
Account No: 1234****56
Account Name: Customer Name
Date and Time: 03-04-2026 00:21:30
Value Date: 03-04-2026
Note: ALAT NIP TRANSFER TO RECIPIENT
Account Balance: 57.95 NGN
"""

WEMA_CREDIT = """
Transaction Notification
Hi Customer,
NGN 10,000.00 has landed into your ALAT Account.

Here is what you need to know:
Reference No: REF789012
Account No: 1234****56
Account Name: Customer Name
Date and Time: 30-03-2026 04:45:09
Value Date: 30-03-2026
Note: NIP:Paystack-Transfer from PiggyVest
Account Balance: 10,040.20 NGN
"""

print("=" * 50)
print("Testing Parser System")
print("=" * 50)

print("\n1. Testing Sterling DEBIT...")
tx = parse_email("alerts@sterling.ng", "Debit Alert", STERLING_DEBIT)
if tx:
    print(f"   ✓ SUCCESS: {tx.tx_type} of ₦{tx.amount}")
    print(f"     Bank: {tx.bank}")
    print(f"     Account: {tx.account_last4}")
else:
    print("   ✗ FAILED")

print("\n2. Testing Sterling CREDIT...")
tx = parse_email("alerts@sterling.ng", "Credit Alert", STERLING_CREDIT)
if tx:
    print(f"   ✓ SUCCESS: {tx.tx_type} of ₦{tx.amount}")
    print(f"     Bank: {tx.bank}")
    print(f"     Narration: {tx.narration[:40]}")
else:
    print("   ✗ FAILED")

print("\n3. Testing Wema DEBIT...")
tx = parse_email("no-reply@alat.ng", "Debit Alert", WEMA_DEBIT)
if tx:
    print(f"   ✓ SUCCESS: {tx.tx_type} of ₦{tx.amount}")
    print(f"     Bank: {tx.bank}")
    print(f"     Balance: ₦{tx.balance}")
else:
    print("   ✗ FAILED")

print("\n4. Testing Wema CREDIT...")
tx = parse_email("no-reply@alat.ng", "Credit Alert", WEMA_CREDIT)
if tx:
    print(f"   ✓ SUCCESS: {tx.tx_type} of ₦{tx.amount}")
    print(f"     Bank: {tx.bank}")
    print(f"     Balance: ₦{tx.balance}")
else:
    print("   ✗ FAILED")

print("\n" + "=" * 50)
print("✓ Test complete!")
print("=" * 50)

