"""Regression tests for department-appropriate technician assignment.

Runs with mocks and never writes to the live Oracle database.
"""
import json
from contextlib import contextmanager
from unittest.mock import patch
from django.test import Client, SimpleTestCase

WARDEN = {'role': 'WARDEN', 'id': 'warden', 'name': 'warden', 'email': None}

@contextmanager
def fake_session(write=False):
    yield object()

class TechnicianAssignmentTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()
        self.session = patch('hostel.common.db.session', side_effect=fake_session)
        self.session.start()
        self.addCleanup(self.session.stop)
        self.auth = patch('hostel.common.authenticate', return_value=WARDEN)
        self.auth.start()
        self.addCleanup(self.auth.stop)

    def assign(self):
        return self.client.post('/api/complaints/1005/assign/',
                                data=json.dumps({'staff_id': 2}),
                                content_type='application/json')

    def test_matching_active_department_is_allowed(self):
        with patch('hostel.views.db.one', return_value={
                'complaint_category': 'Electrical', 'staff_department': ' electrical ',
                'staff_status': 'ACTIVE'}), patch('hostel.views.db.call') as procedure:
            response = self.assign()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(procedure.call_args.args[1], 'sp_assign_complaint')
        self.assertEqual(procedure.call_args.args[2], [1005, 2, 'WARDEN:warden'])

    def test_plumbing_technician_rejected_for_electrical_complaint(self):
        with patch('hostel.views.db.one', return_value={
                'complaint_category': 'Electrical', 'staff_department': 'Plumbing',
                'staff_status': 'ACTIVE'}), patch('hostel.views.db.call') as procedure:
            response = self.assign()
        self.assertEqual(response.status_code, 400)
        self.assertIn('department', response.json()['error'])
        procedure.assert_not_called()

    def test_inactive_matching_technician_rejected(self):
        with patch('hostel.views.db.one', return_value={
                'complaint_category': 'Electrical', 'staff_department': 'Electrical',
                'staff_status': 'INACTIVE'}), patch('hostel.views.db.call') as procedure:
            response = self.assign()
        self.assertEqual(response.status_code, 400)
        self.assertIn('active', response.json()['error'])
        procedure.assert_not_called()

    def test_missing_technician_rejected(self):
        with patch('hostel.views.db.one', return_value=None), patch('hostel.views.db.call') as procedure:
            response = self.assign()
        self.assertEqual(response.status_code, 404)
        procedure.assert_not_called()
