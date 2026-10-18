"""Frontend route and role-scoped summary tests (no Oracle required)."""
from contextlib import contextmanager
from unittest.mock import patch

from django.test import Client, SimpleTestCase


@contextmanager
def fake_session(write=False):
    yield object()


class FrontendTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    def test_root_serves_same_origin_frontend(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Smart Hostel')
        self.assertContains(response, '/static/hostel/app.js')
        self.assertContains(response, '/static/hostel/app.css')

    def test_summary_not_public(self):
        with patch('hostel.common.db.session', side_effect=fake_session):
            response = self.client.get('/api/complaints/summary/')
        self.assertEqual(response.status_code, 401)

    def test_student_summary_filters_by_authenticated_id(self):
        actor = {'role': 'STUDENT', 'id': 99, 'name': 'Student'}
        with patch('hostel.common.db.session', side_effect=fake_session), \
             patch('hostel.common.authenticate', return_value=actor), \
             patch('hostel.views.db.one', return_value={'total': 3}) as query:
            response = self.client.get('/api/complaints/summary/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['total'], 3)
        self.assertIn('c.student_id = ?', query.call_args.args[1])
        self.assertEqual(query.call_args.args[2], [99])

    def test_staff_summary_uses_exists_to_avoid_duplicate_assignments(self):
        actor = {'role': 'STAFF', 'id': 11, 'name': 'Staff'}
        with patch('hostel.common.db.session', side_effect=fake_session), \
             patch('hostel.common.authenticate', return_value=actor), \
             patch('hostel.views.db.one', return_value={'total': 1}) as query:
            response = self.client.get('/api/complaints/summary/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('EXISTS', query.call_args.args[1])
        self.assertEqual(query.call_args.args[2], [11])

    def test_warden_summary_not_filtered(self):
        actor = {'role': 'WARDEN', 'id': 'warden', 'name': 'warden'}
        with patch('hostel.common.db.session', side_effect=fake_session), \
             patch('hostel.common.authenticate', return_value=actor), \
             patch('hostel.views.db.one', return_value={'total': 10}) as query:
            response = self.client.get('/api/complaints/summary/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(query.call_args.args[2], [])
