import json
from cds_backend.app import app


def test_donation_flow():
    import io
    with app.test_client() as client:
        # prepare a fake proof file
        proof = (io.BytesIO(b"fake-receipt-data"), 'receipt.png')
        data = {
            'fullname': 'TT',
            'email': 't@t.com',
            'phone': '080',
            'amount': '500',
            'proof': proof
        }
        # create donation (multipart/form-data)
        r = client.post('/donate', data=data, content_type='multipart/form-data')
        assert r.status_code == 201
        resp_json = r.get_json()
        assert 'reference' in resp_json
        ref = resp_json['reference']

        # pending list requires admin key
        resp = client.get('/pending-donations', headers={'X-ADMIN-KEY': 'admin123'})
        assert resp.status_code == 200
        pendings = resp.get_json()
        assert any(p['reference'] == ref and p.get('proof_filename') for p in pendings)

        # validate
        resp = client.post('/admin/validate-donation', headers={'X-ADMIN-KEY': 'admin123'}, json={'reference': ref})
        assert resp.status_code == 200

        # now paid-users should include it and proof filename preserved
        resp = client.get('/paid-users')
        assert resp.status_code == 200
        paid = resp.get_json()
        assert any(p['reference'] == ref and p['status'] == 'paid' and p.get('proof_filename') for p in paid)
