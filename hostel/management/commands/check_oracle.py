"""python manage.py check_oracle -- safe and read-only Oracle ODBC preflight."""
from django.core.management.base import BaseCommand, CommandError
from hostel.diagnostics import run_diagnostics


class Command(BaseCommand):
    help = 'Check ODBC DSN, Oracle connection, objects, and privileges (read-only).'

    def handle(self, *args, **options):
        report = run_diagnostics()
        for item in report.findings:
            style = {'PASS': self.style.SUCCESS,
                     'WARN': self.style.WARNING,
                     'FAIL': self.style.ERROR}[item.level]
            self.stdout.write(style(f'[{item.level}] {item.name}: {item.detail}'))
        passed = sum(f.level == 'PASS' for f in report.findings)
        warned = sum(f.level == 'WARN' for f in report.findings)
        failed = sum(f.level == 'FAIL' for f in report.findings)
        self.stdout.write(f'Oracle diagnostic summary: {passed} passed, {warned} warnings, {failed} failures.')
        if report.failed:
            raise CommandError('Oracle ODBC checks failed. Fix the failures above and retry.')
