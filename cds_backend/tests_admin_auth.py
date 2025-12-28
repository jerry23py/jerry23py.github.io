from cds_backend.app import app, generate_admin_token


def test_admin_login_and_protected_routes():
    with app.test_client() as client:
        # login with wrong password
        r = client.post('/admin/login', json={'password': 'wrong'})
        assert r.status_code == 401

        # login with correct password
        r = client.post('/admin/login', json={'password': 'admin123'})
        assert r.status_code == 200
        data = r.get_json()
        assert 'token' in data
        token = data['token']

        # try to access protected pending-donations without token
        r2 = client.get('/pending-donations')
        assert r2.status_code == 401

        # now with Authorization header
        r3 = client.get('/pending-donations', headers={'Authorization': f'Bearer {token}'})
        assert r3.status_code == 200

        # upload a proof and get protected proof link
        import io
        proof = (io.BytesIO(b"receipt"), 'proof.png')
        r4 = client.post('/donate', data={'fullname':'A','email':'a@b','phone':'0','amount':'50','proof': proof}, content_type='multipart/form-data')
        assert r4.status_code == 201
        ref = r4.get_json()['reference']

        # read pending donations to get proof filename
        r5 = client.get('/pending-donations', headers={'Authorization': f'Bearer {token}'})
        pend = r5.get_json()
        assert any(p.get('proof_filename') for p in pend)
        proof_name = next(p['proof_filename'] for p in pend if p.get('proof_filename'))

        # access protected proof without token -> 401
        r6 = client.get(f'/protected-proof/{proof_name}')
        assert r6.status_code == 401

        # access protected proof with token
        r7 = client.get(f'/protected-proof/{proof_name}', query_string={'token': token})
        assert r7.status_code == 200

        # validate donation and ensure approval info is recorded
        ref = pend[0]['reference']
        rr = client.post('/admin/validate-donation', headers={'Authorization': f'Bearer {token}'}, json={'reference': ref})
        assert rr.status_code == 200
        assert 'approved_by' in rr.get_json()

        # check donation-status shows approval info
        status = client.get(f'/donation-status/{ref}')
        assert status.status_code == 200
        sjson = status.get_json()
        assert sjson.get('status') == 'paid'
        assert sjson.get('approved_by') is not None

