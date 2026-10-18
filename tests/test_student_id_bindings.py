"""Regressions for Oracle NUMBER -> Decimal -> ODBC student page failures."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from hostel import database as db
from hostel import security


class OracleIdBindingTests(SimpleTestCase):
    def test_student_login_coerces_oracle_decimal_pk_to_int(self):
        row = {'id': Decimal('5'), 'name': 'Test Student', 'email': 'student@test.local',
               'status': 'ACTIVE', 'password': 'stored-hash'}
        with patch('hostel.security.db.one', return_value=row), \
             patch('hostel.security.check_password', return_value=True), \
             patch('hostel.security.issue_token', return_value='token') as issued:
            result = security.verify_login(object(), 'STUDENT', row['email'], 'password1234')
        self.assertEqual(result['user']['id'], 5)
        self.assertIs(type(result['user']['id']), int)
        self.assertEqual(issued.call_args.args[1], 5)

    def test_staff_login_also_coerces_decimal_pk(self):
        row = {'id': Decimal('9'), 'name': 'Technician', 'email': 'staff@test.local',
               'status': 'ACTIVE', 'password': 'stored-hash'}
        with patch('hostel.security.db.one', return_value=row), \
             patch('hostel.security.check_password', return_value=True), \
             patch('hostel.security.issue_token', return_value='token'):
            result = security.verify_login(object(), 'STAFF', row['email'], 'password1234')
        self.assertIs(type(result['user']['id']), int)
        self.assertEqual(result['user']['id'], 9)

    def test_token_auth_returns_int_even_if_odbc_supplies_decimal(self):
        row = {'id': Decimal('5'), 'name': 'Test Student', 'email': 'student@test.local',
               'status': 'ACTIVE', 'password': 'stored-hash'}
        claims = {'sub': 'STUDENT:5', 'role': 'STUDENT', 'pwd': security.pw_version('stored-hash')}
        req = SimpleNamespace(headers={'Authorization': 'Bearer demo-token'})
        with patch('hostel.security.db.one', return_value=row), \
             patch('hostel.security.jwt.decode', return_value=claims):
            actor = security.authenticate(object(), req)
        self.assertEqual(actor['id'], 5)
        self.assertIs(type(actor['id']), int)
        self.assertNotIn('password', actor)

    def test_integral_decimal_bind_is_converted_before_pyodbc(self):
        class FakeCursor:
            def __init__(self):
                self.params = None
            def execute(self, sql, params):
                self.params = params
            def close(self):
                pass
        cursor = FakeCursor()
        connection = SimpleNamespace(cursor=lambda: cursor)
        fake_pyodbc = SimpleNamespace(Error=Exception)
        import sys
        with patch.dict(sys.modules, {'pyodbc': fake_pyodbc}):
            result = db._execute(connection, 'SELECT 1 FROM dual WHERE ? = ?',
                                 [Decimal('5'), Decimal('2.5')])
        self.assertIs(result, cursor)
        self.assertEqual(cursor.params, (5, Decimal('2.5')))
        self.assertIs(type(cursor.params[0]), int)

    def test_non_integral_or_zero_actor_id_rejected(self):
        for raw in (Decimal('2.5'), Decimal('0'), True):
            with self.assertRaises(security.ApiError):
                security._normalize_numeric_id(raw)
