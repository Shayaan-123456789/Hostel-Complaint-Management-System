"""Read-only ODBC and permission diagnostics: no real Oracle required."""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from hostel import diagnostics as diag


class DiagnosticsTests(SimpleTestCase):
    def test_known_connection_errors_have_actionable_messages(self):
        for code in ('ORA-01017', 'ORA-01031', 'ORA-00942', 'ORA-12514', 'IM002'):
            reported, explanation = diag.classify_exception(Exception(f'[HY000] {code}: sample'))
            self.assertEqual(reported, code)
            self.assertTrue(explanation)

    def test_wrapped_error_extracts_safe_cause(self):
        try:
            raise RuntimeError('[HY000] ORA-01031: no privileges')
        except RuntimeError as underlying:
            try:
                raise ValueError('generic database rejection') from underlying
            except ValueError as outer:
                code, _ = diag.classify_exception(outer)
        self.assertEqual(code, 'ORA-01031')

    def test_all_expected_schema_objects_match_bundle(self):
        from pathlib import Path
        import re
        root = Path(__file__).resolve().parents[1] / 'oracle_sql'
        ddl = (root / '01_ddl.sql').read_text().upper()
        procs = (root / '03_procedures.sql').read_text().upper()
        trigs = (root / '02_triggers.sql').read_text().upper()
        for kind, names, source in [
            ('TABLE', diag.EXPECTED['TABLE'], ddl),
            ('VIEW', diag.EXPECTED['VIEW'], ddl),
            ('SEQUENCE', diag.EXPECTED['SEQUENCE'], ddl),
            ('PROCEDURE', diag.EXPECTED['PROCEDURE'], procs),
            ('TRIGGER', diag.EXPECTED['TRIGGER'], trigs),
        ]:
            for name in names:
                self.assertRegex(source, rf'CREATE (?:OR REPLACE )?{kind} {name}\b')

    @patch('hostel.database.run')
    @patch('hostel.database.all_rows')
    @patch('hostel.database.one')
    def test_preflight_never_executes_dml(self, identity, rows, run):
        identity.return_value = {'session_user': 'HOSTEL_OWNER', 'current_schema': 'HOSTEL_OWNER'}
        objects = [dict(object_name=name, object_type=kind, status='VALID')
                   for kind, names in diag.EXPECTED.items() for name in names]
        rows.side_effect = lambda _conn, sql, _params=(): objects if 'all_objects' in sql.lower() else []
        report = diag.CheckReport()
        diag.inspect_connection(object(), report)
        self.assertFalse(report.failed)
        self.assertEqual(run.call_count, 1)
        self.assertIn('DECLARE v_test', run.call_args.args[1])
        for call in rows.call_args_list:
            text = call.args[1].strip().upper()
            self.assertTrue(text.startswith('SELECT'), text)

    @patch('hostel.database.run')
    @patch('hostel.database.all_rows')
    @patch('hostel.database.one')
    def test_missing_cross_schema_grant_is_reported(self, identity, rows, _run):
        identity.return_value = {'session_user': 'HOSTEL_APP', 'current_schema': 'HOSTEL_OWNER'}
        objects = [dict(object_name=name, object_type=kind, status='VALID')
                   for kind, names in diag.EXPECTED.items() for name in names]
        rows.side_effect = lambda _conn, sql, _params=(): objects if 'all_objects' in sql.lower() else []
        report = diag.CheckReport()
        diag.inspect_connection(object(), report)
        self.assertTrue(report.failed)
        self.assertTrue(any(f.name == 'Direct grants ROOM' for f in report.findings))
        self.assertTrue(any(f.name == 'Column grants STUDENT' for f in report.findings))
        self.assertTrue(any(f.name == 'EXECUTE SP_SUBMIT_COMPLAINT' for f in report.findings))
