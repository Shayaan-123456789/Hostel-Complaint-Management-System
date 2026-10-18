"""Regression: a valid STUDENT/STAFF token must produce an actor with role.

Unlike existing tests, these do NOT mock hostel.common.authenticate.
They exercise the actual token-to-actor function through HTTP endpoints,
with only Oracle/ODBC calls mocked. No test writes to the real database.
"""
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, SimpleTestCase

from hostel.security import pw_version


@contextmanager
def fake_session(write=False):
    yield object()


class RealActorRoleRegressionTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()
        self.pw_hash = 'not-a-real-login-hash'
        self.session = patch('hostel.common.db.session', side_effect=fake_session)
        self.session.start()
        self.addCleanup(self.session.stop)

    def identity(self, role='STUDENT', identity=5):
        # jwt.decode is mocked, NOT the authenticate function. This
        # reproduces the code path that previously raised KeyError 'role'.
        claims = {'sub': f'{role}:{identity}', 'role': role,
                  'pwd': pw_version(self.pw_hash)}
        token_patch = patch('hostel.security.jwt.decode', return_value=claims)
        token_patch.start()
        self.addCleanup(token_patch.stop)
        return {'HTTP_AUTHORIZATION': 'Bearer fake-valid-token'}

    def fake_row(self, conn, sql, params=()):
        if 'FROM student' in sql or 'FROM staff' in sql:
            return {'id': Decimal('5'), 'name': 'Test Account',
                    'email': 'test@example.org', 'status': 'ACTIVE',
                    'password': self.pw_hash}
        return {'total': 0, 'open_count': 0, 'assigned_count': 0,
                'in_progress_count': 0, 'resolved_count': 0, 'closed_count': 0}

    def test_student_me_returns_role_and_no_password(self):
        with patch('hostel.security.db.one', side_effect=self.fake_row):
            resp = self.client.get('/api/auth/me/', **self.identity())
        self.assertEqual(resp.status_code, 200)
        user = resp.json()['user']
        self.assertEqual(user['role'], 'STUDENT')
        self.assertEqual(user['id'], 5)
        self.assertNotIn('password', user)
        self.assertNotIn('status', user)

    def test_staff_me_returns_role_and_no_password(self):
        with patch('hostel.security.db.one', side_effect=self.fake_row):
            resp = self.client.get('/api/auth/me/', **self.identity('STAFF'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['user']['role'], 'STAFF')

    def test_student_complaints_endpoint_scopes_to_token_identity(self):
        with patch('hostel.security.db.one', side_effect=self.fake_row), \
             patch('hostel.views.db.value', return_value=0), \
             patch('hostel.views.db.page', return_value=[]) as page:
            resp = self.client.get('/api/complaints/?limit=8', **self.identity())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['complaints'], [])
        self.assertIn('v.student_id = ?', page.call_args.args[1])
        self.assertEqual(page.call_args.args[2], [5])

    def test_student_overview_scopes_to_token_identity(self):
        with patch('hostel.security.db.one', side_effect=self.fake_row) as query:
            resp = self.client.get('/api/complaints/summary/', **self.identity())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['summary']['total'], 0)
        self.assertIn('c.student_id = ?', query.call_args.args[1])
        self.assertEqual(query.call_args.args[2], [5])

    def test_staff_complaints_scopes_to_assigned_only(self):
        with patch('hostel.security.db.one', side_effect=self.fake_row), \
             patch('hostel.views.db.value', return_value=0), \
             patch('hostel.views.db.page', return_value=[]) as page:
            resp = self.client.get('/api/complaints/', **self.identity('STAFF'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('EXISTS', page.call_args.args[1])
        self.assertIn('a.staff_id = ?', page.call_args.args[1])
        self.assertEqual(page.call_args.args[2], [5])

    def test_staff_denied_warden_endpoint_using_real_auth(self):
        with patch('hostel.security.db.one', side_effect=self.fake_row):
            resp = self.client.get('/api/admin/dashboard/', **self.identity('STAFF'))
        self.assertEqual(resp.status_code, 403)
