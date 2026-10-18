"""Read-only probe for student pages using the same SQL as Django API.

Usage: python manage.py check_student_queries --student-id 5
No write queries, credentials, passwords, tokens, titles, or photos are printed.
"""
import re
from django.core.management.base import BaseCommand, CommandError
from hostel import database as db


class Command(BaseCommand):
    help = 'Read-only diagnostics for student overview and complaint endpoints'

    def add_arguments(self, parser):
        parser.add_argument('--student-id', type=int, required=True)

    def handle(self, *args, **options):
        student_id = options['student_id']
        if student_id <= 0:
            raise CommandError('student-id must be a positive integer.')
        tests = (
            ('Student row', lambda conn: db.one(conn,
                'SELECT student_id, status FROM student WHERE student_id = ?', [student_id])),
            ('Complaint count from view', lambda conn: db.value(conn,
                'SELECT COUNT(*) FROM v_complaint_details v WHERE v.student_id = ?', [student_id])),
            ('Paginated complaint list', lambda conn: db.page(conn,
                """SELECT v.* FROM v_complaint_details v WHERE v.student_id = ?
                ORDER BY CASE v.priority WHEN 'URGENT' THEN 1 WHEN 'HIGH' THEN 2
                    WHEN 'MEDIUM' THEN 3 ELSE 4 END,
                    v.created_date DESC, v.complaint_id DESC""", [student_id], 8, 0)),
            ('Overview summary', lambda conn: db.one(conn,
                """SELECT COUNT(*) AS total,
                    SUM(CASE WHEN c.status = 'OPEN' THEN 1 ELSE 0 END) AS open_count,
                    SUM(CASE WHEN c.status = 'ASSIGNED' THEN 1 ELSE 0 END) AS assigned_count,
                    SUM(CASE WHEN c.status = 'IN_PROGRESS' THEN 1 ELSE 0 END) AS in_progress_count,
                    SUM(CASE WHEN c.status = 'RESOLVED' THEN 1 ELSE 0 END) AS resolved_count,
                    SUM(CASE WHEN c.status = 'CLOSED' THEN 1 ELSE 0 END) AS closed_count
                   FROM complaint c WHERE c.student_id = ?""", [student_id])),
        )
        failures = 0
        for label, test in tests:
            try:
                with db.session() as conn:
                    value = test(conn)
                if label == 'Student row' and not value:
                    raise ValueError('Student ID not found.')
                count = len(value) if label == 'Paginated complaint list' else None
                msg = f' [{count} row(s)]' if count is not None else ''
                self.stdout.write(self.style.SUCCESS(f'[PASS] {label}{msg}'))
            except Exception as exc:
                failures += 1
                # Show SQL error codes but not SQL parameters, personal data,
                # passwords or connection strings.
                chain = []
                cur = exc
                while cur is not None and len(chain) < 4:
                    chain.extend(re.findall(r'ORA-\d{5}|(?:HY|IM)[A-Z0-9]{3}', str(cur)))
                    cur = cur.__cause__
                codes = ', '.join(dict.fromkeys(chain)) or type(exc).__name__
                self.stderr.write(self.style.ERROR(f'[FAIL] {label}: {codes}'))
        if failures:
            raise CommandError(f'{failures} student query check(s) failed. Review Django server traceback for the first failure.')
        self.stdout.write(self.style.SUCCESS('All student read-only database queries passed.'))
