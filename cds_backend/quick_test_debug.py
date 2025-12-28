import os, sys
# Ensure parent folder is on sys.path so 'cds_backend' package can be imported when running this script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from cds_backend.app import app

with app.test_client() as c:
    # OPTIONS preflight for admin bank accounts
    r = c.open('/admin/bank-accounts', method='OPTIONS')
    print('OPTIONS status:', r.status_code)
    print('CORS headers:')
    for k in ['Access-Control-Allow-Origin','Access-Control-Allow-Methods','Access-Control-Allow-Headers','Access-Control-Allow-Credentials']:
        print(k, '=>', r.headers.get(k))

    # POST without token should be unauthorized
    r2 = c.post('/admin/bank-accounts', data={'bank_name':'A','account_name':'B','account_number':'123'})
    print('POST without token status:', r2.status_code, r2.get_json())

    # login to get a token
    login = c.post('/admin/login', json={'password':'admin123'})
    token = login.get_json().get('token')
    print('Login token present?', bool(token))

    # POST using query token (simulate browser non-preflight form POST)
    r3 = c.post(f'/admin/bank-accounts?token={token}', data={'bank_name':'Test Bank','account_name':'TB','account_number':'999'})
    print('POST with query token status:', r3.status_code, r3.get_json())

    # Call debug request endpoint using query token
    r4 = c.post(f'/admin/_debug-request?token={token}', data={'test_field':'x'}, content_type='application/x-www-form-urlencoded')
    print('Debug POST status:', r4.status_code)
    print('Debug JSON snippet:', {k: r4.get_json().get(k) for k in ['method','path','args','body']})
