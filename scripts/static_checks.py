"""Dependency-free static smoke test for source organization and route targets."""
import ast
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root / 'smart_hostel/urls.py').read_text()
views = ast.parse((root / 'hostel/views.py').read_text())
functions = {item.name for item in views.body if isinstance(item, ast.FunctionDef)}
refs = set(re.findall(r'views\.(\w+)', source))
missing = sorted(refs - functions)
assert not missing, f'Missing view implementations: {missing}'
assert len(refs) >= 21
sql = (root / 'oracle_sql/01_ddl.sql').read_text().lower()
actual = set(re.findall(r'create table (\w+)', sql))
expected = {
    'room', 'student', 'category', 'staff', 'complaint',
    'complaint_photo', 'complaint_assignment', 'complaint_status', 'complaint_feedback',
}
assert actual == expected, (actual, expected)
code = (root / 'hostel/database.py').read_text()
assert 'sp_submit_complaint' in code and 'sp_register_student' in code
assert 'CURRVAL' in code
print(f'Static checks passed: {len(refs)} routes, 9 unmodified Oracle tables.')
