"""Only existing Oracle CATEGORY names are valid staff departments.

No live Oracle database is contacted.  Tests exercise the real Django
route and staff views, with database adapter calls mocked out.
"""
import json
from contextlib import contextmanager
from unittest.mock import patch

from django.test import Client, SimpleTestCase


WARDEN = {'role': 'WARDEN', 'id': 'warden', 'name': 'warden', 'email': None}
STUDENT = {'role': 'STUDENT', 'id': 5, 'name': 'Test Student', 'email': 'student@test.edu'}


@contextmanager
def fake_session(write=False):
    yield object()


class StaffDepartmentTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()
        self.s = patch('hostel.common.db.session', side_effect=fake_session)
        self.s.start()
        self.addCleanup(self.s.stop)
        self.auth = patch('hostel.common.authenticate', return_value=WARDEN)
        self.auth.start()
        self.addCleanup(self.auth.stop)

    @staticmethod
    def staff(name='Technician', department='Electrical'):
        return {'name': name, 'email': 'tech@example.org',
                'password': 'ExamplePass2026!', 'department': department, 'phone': ''}

    def post_staff(self, department='Electrical'):
        return self.client.post('/api/admin/staff/create/',
                                data=json.dumps(self.staff(department=department)),
                                content_type='application/json')

    def test_creating_staff_uses_canonical_category_name(self):
        with patch('hostel.views.db.one', return_value={'category_name': 'Electrical'}) as lookup, \
             patch('hostel.views.db.run') as insert, \
             patch('hostel.views.db.value', return_value=15):
            response = self.post_staff(' electrical ')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['staff_id'], 15)
        self.assertIn('UPPER(TRIM(category_name))', lookup.call_args.args[1])
        self.assertEqual(lookup.call_args.args[2], ['electrical'])
        self.assertEqual(insert.call_args.args[2][3], 'Electrical')

    def test_unknown_department_rejected_before_insert(self):
        with patch('hostel.views.db.one', return_value=None), \
             patch('hostel.views.db.run') as insert:
            response = self.post_staff('Other')
        self.assertEqual(response.status_code, 400)
        self.assertIn('existing complaint category', response.json()['error'])
        insert.assert_not_called()

    def test_missing_department_rejected_before_insert(self):
        form = self.staff()
        del form['department']
        with patch('hostel.views.db.run') as insert:
            response = self.client.post('/api/admin/staff/create/',
                                        data=json.dumps(form), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        insert.assert_not_called()

    def test_edit_staff_normalizes_department(self):
        with patch('hostel.views.db.one', side_effect=[
            {'staff_id': 9}, {'category_name': 'Plumbing'},
        ]) as lookup, patch('hostel.views.db.run') as update:
            response = self.client.patch('/api/admin/staff/9/',
                                         data=json.dumps({'department': ' plumbing '}),
                                         content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(lookup.call_count, 2)
        self.assertEqual(update.call_args.args[2], ['Plumbing', 9])

    def test_edit_staff_rejects_unknown_department(self):
        with patch('hostel.views.db.one', side_effect=[{'staff_id': 9}, None]), \
             patch('hostel.views.db.run') as update:
            response = self.client.patch('/api/admin/staff/9/',
                                         data=json.dumps({'department': 'NotReal'}),
                                         content_type='application/json')
        self.assertEqual(response.status_code, 400)
        update.assert_not_called()

    def test_student_cannot_create_staff(self):
        with patch('hostel.common.authenticate', return_value=STUDENT), \
             patch('hostel.views.db.one') as lookup, \
             patch('hostel.views.db.run') as insert:
            response = self.post_staff()
        self.assertEqual(response.status_code, 403)
        lookup.assert_not_called()
        insert.assert_not_called()
