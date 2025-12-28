from cds_backend.app import app
import json

with app.test_client() as client:
    r = client.post('/admin/login', json={'password':'admin123'})
    token = r.get_json().get('token')
    headers = {'Authorization': 'Bearer ' + token}
    d = client.get('/admin/_debug-db', headers=headers)
    print(json.dumps(d.get_json(), indent=2))
