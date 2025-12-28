from cds_backend.app import app


def test_bank_accounts_crud():
    with app.test_client() as client:
        # public list initially empty (or at least returns 200)
        r = client.get('/bank-accounts')
        assert r.status_code == 200
        before = r.get_json()

        # unauthenticated create should fail
        r = client.post('/admin/bank-accounts', json={'bank_name':'Bank A','account_name':'Charity','account_number':'012345'},)
        assert r.status_code == 401

        # login as admin to get token
        r = client.post('/admin/login', json={'password': 'admin123'})
        assert r.status_code == 200
        token = r.get_json()['token']

        headers = {'Authorization': f'Bearer {token}'}

        # create a bank account
        r = client.post('/admin/bank-accounts', json={'bank_name':'Bank A','account_name':'Charity','account_number':'012345','bank_type':'savings'}, headers=headers)
        assert r.status_code == 201
        data = r.get_json()
        assert 'id' in data
        acc_id = data['id']

        # admin list should show the account
        r = client.get('/admin/bank-accounts', headers=headers)
        assert r.status_code == 200
        admin_list = r.get_json()
        assert any(a['id'] == acc_id for a in admin_list)

        # public list should show it (active default = true)
        r = client.get('/bank-accounts')
        assert r.status_code == 200
        pub_list = r.get_json()
        assert any(a['id'] == acc_id for a in pub_list)

        # toggle active -> set to false
        r = client.put(f'/admin/bank-accounts/{acc_id}', json={'active': False}, headers=headers)
        assert r.status_code == 200

        # public list should no longer include it
        r = client.get('/bank-accounts')
        assert r.status_code == 200
        pub_list = r.get_json()
        assert not any(a['id'] == acc_id for a in pub_list)

        # delete the account
        r = client.delete(f'/admin/bank-accounts/{acc_id}', headers=headers)
        assert r.status_code == 200

        # admin list should not include it
        r = client.get('/admin/bank-accounts', headers=headers)
        assert r.status_code == 200
        admin_list = r.get_json()
        assert not any(a['id'] == acc_id for a in admin_list)

        # create bank again to validate donation association
        r = client.post('/admin/bank-accounts', json={'bank_name':'Bank B','account_name':'Charity B','account_number':'33344','bank_type':'current'}, headers=headers)
        assert r.status_code == 201
        new_acc = r.get_json()['id']
        # submit a donation choosing that bank account
        import io
        proof = (io.BytesIO(b"receipt"), 'proof.png')
        r = client.post('/donate', data={'fullname':'Z','email':'z@z','phone':'000','amount':'300','proof': proof, 'bank_account_id': str(new_acc)}, content_type='multipart/form-data')
        assert r.status_code == 201
        # now pending-donations (admin) should include bank_account_id on that entry
        r = client.get('/pending-donations', headers=headers)
        assert r.status_code == 200
        pend = r.get_json()
        assert any(p.get('bank_account_id') == new_acc for p in pend)
