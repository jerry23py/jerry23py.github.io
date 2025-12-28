from cds_backend.app import app

with app.test_client() as c:
    r = c.get('/bank-accounts')
    print('status', r.status_code)
    print('json', r.get_json())
