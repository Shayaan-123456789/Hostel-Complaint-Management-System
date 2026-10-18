"""Tests run without Oracle using mocked ODBC calls: python manage.py test tests"""
import json
from contextlib import contextmanager
from unittest.mock import patch

from django.test import SimpleTestCase, Client


@contextmanager
def fake_session(write=False):
    yield object()


STUDENT = {'role': 'STUDENT', 'id': 1, 'name': 'Student One', 'email': 's@test.edu'}
WARDEN = {'role': 'WARDEN', 'id': 'warden', 'name': 'warden', 'email': None}
STAFF = {'role': 'STAFF', 'id': 2, 'name': 'Staff Two', 'email': 't@test.edu'}


class EndpointSecurityTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()
        self.connection_patch = patch('hostel.common.db.session', side_effect=fake_session)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    def as_role(self, actor):
        auth = patch('hostel.common.authenticate', return_value=actor)
        auth.start()
        self.addCleanup(auth.stop)

    def test_anonymous_cannot_read_complaints(self):
        with patch('hostel.common.authenticate', side_effect=__import__('hostel.security', fromlist=['ApiError']).ApiError('Authentication required.', 401)):
            resp = self.client.get('/api/complaints/')
        self.assertEqual(resp.status_code, 401)

    def test_student_cannot_assign(self):
        self.as_role(STUDENT)
        resp = self.client.post('/api/complaints/1001/assign/', data=json.dumps({'staff_id': 2}), content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_staff_cannot_close(self):
        self.as_role(STAFF)
        resp = self.client.post('/api/complaints/1001/status/', data=json.dumps({'status': 'CLOSED'}), content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_student_create_calls_real_stored_procedure_name(self):
        self.as_role(STUDENT)
        with patch('hostel.views.db.call_with_id', return_value=1001) as procedure:
            resp = self.client.post('/api/complaints/', data=json.dumps({
                'category_id': 1, 'title': 'Leaking tap', 'description': 'Water leaks every day.',
                'priority': 'HIGH',
            }), content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['complaint_id'], 1001)
        self.assertEqual(procedure.call_args.args[1], 'sp_submit_complaint')
        self.assertEqual(procedure.call_args.args[2][0], STUDENT['id'])

    def test_warden_assigns_with_audited_identity(self):
        self.as_role(WARDEN)
        with patch('hostel.views.db.one', return_value={
                'complaint_category': 'Electrical',
                'staff_department': 'Electrical',
                'staff_status': 'ACTIVE',
            }), patch('hostel.views.db.call') as procedure:
            resp = self.client.post('/api/complaints/1001/assign/',
                                    data=json.dumps({'staff_id': 2}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(procedure.call_args.args[1], 'sp_assign_complaint')
        self.assertEqual(procedure.call_args.args[2], [1001, 2, 'WARDEN:warden'])

    def test_staff_must_own_active_assignment_to_update(self):
        self.as_role(STAFF)
        with patch('hostel.views._active_assignee', return_value=False):
            resp = self.client.post('/api/complaints/1001/status/',
                                    data=json.dumps({'status': 'IN_PROGRESS'}), content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_warden_only_dashboard(self):
        self.as_role(STUDENT)
        resp = self.client.get('/api/admin/dashboard/')
        self.assertEqual(resp.status_code, 403)

    def test_status_requires_resolution_remark(self):
        self.as_role(WARDEN)
        resp = self.client.post('/api/complaints/1001/status/',
                                data=json.dumps({'status': 'RESOLVED'}), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_student_cannot_create_staff(self):
        self.as_role(STUDENT)
        resp = self.client.post('/api/admin/staff/create/', data=json.dumps({}), content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_feedback_requires_rating_1_to_5(self):
        self.as_role(STUDENT)
        resp = self.client.post('/api/complaints/1001/feedback/',
                                data=json.dumps({'rating': 6}), content_type='application/json')
        self.assertEqual(resp.status_code, 400)
