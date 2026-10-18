"""Generate HOSTEL_ADMIN_PASSWORD_HASH without exposing a password in shell args."""
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_hostel.settings')
import django
django.setup()
from django.contrib.auth.hashers import make_password

password = getpass.getpass('New warden password (10+ characters): ')
confirm = getpass.getpass('Confirm password: ')
if len(password) < 10 or password != confirm:
    raise SystemExit('Passwords differ or are shorter than 10 characters.')
print('\nCopy the following hash into HOSTEL_ADMIN_PASSWORD_HASH in .env:')
print(make_password(password))
