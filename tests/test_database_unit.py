"""Pure helper tests; no live Oracle required."""
from decimal import Decimal
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from hostel import database as db
from hostel.common import integer
from hostel.security import ApiError, pw_version


class DatabaseUnitTests(SimpleTestCase):
    def test_generated_id_uses_sequence_currval_on_same_connection(self):
        conn = object()
        with patch('hostel.database.run') as run, patch('hostel.database.value', return_value=1001) as scalar:
            actual = db.call_with_id(conn, 'sp_submit_complaint', [1, 2, 't', 'd', 'HIGH', None])
        self.assertEqual(actual, 1001)
        self.assertIn('sp_submit_complaint', run.call_args.args[1])
        self.assertIn('seq_complaint.CURRVAL', scalar.call_args.args[1])
        self.assertIs(scalar.call_args.args[0], conn)

    def test_procedure_name_cannot_be_user_defined(self):
        with self.assertRaises(ValueError):
            db.call(object(), 'DROP TABLE student', [])

    def test_numbers_round_trip(self):
        self.assertEqual(db.json_ready({'id': Decimal(2), 'score': Decimal('4.5')}), {'id': 2, 'score': 4.5})

    def test_integer_rejects_boolean_and_fraction(self):
        with self.assertRaises(ApiError):
            integer({'student_id': True}, 'student_id')
        with self.assertRaises(ApiError):
            integer({'student_id': '2.5'}, 'student_id')

    def test_password_version_changes_with_hash(self):
        self.assertNotEqual(pw_version('one'), pw_version('two'))
