import sys, os, traceback
# ensure parent workspace path on sys.path so cds_backend package imports resolve when running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from cds_backend import tests_admin_auth, tests_bank_accounts, tests_donations

TESTS = [
    tests_admin_auth.test_admin_login_and_protected_routes,
    tests_bank_accounts.test_bank_accounts_crud,
    tests_donations.test_donation_flow,
]

failures = []
for t in TESTS:
    try:
        t()
        print(f"PASS: {t.__name__}")
    except Exception as e:
        print(f"FAIL: {t.__name__}")
        traceback.print_exc()
        failures.append((t.__name__, str(e)))

print('\nSummary:')
print(f"Passed: {len(TESTS)-len(failures)}/{len(TESTS)}")
if failures:
    print('Failures:')
    for name, err in failures:
        print('-', name, err)
