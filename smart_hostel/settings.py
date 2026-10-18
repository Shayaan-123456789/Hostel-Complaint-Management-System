"""Django API over the existing Oracle schema; no Django ORM tables/migrations."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
DEBUG = os.getenv('DJANGO_DEBUG', '0') == '1'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY or SECRET_KEY.startswith('REPLACE_'):
    if DEBUG:
        SECRET_KEY = 'INSECURE-DEVELOPMENT-ONLY-CHANGE-BEFORE-DEPLOYING'
    else:
        raise RuntimeError('Set DJANGO_SECRET_KEY in .env for deployment.')

ALLOWED_HOSTS = [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]
ROOT_URLCONF = 'smart_hostel.urls'
INSTALLED_APPS = ['django.contrib.staticfiles', 'hostel']
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'hostel.middleware.AllowedOriginsMiddleware',
]
DATABASES = {'default': {'ENGINE': 'django.db.backends.dummy'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
TIME_ZONE = 'UTC'
APPEND_SLASH = False

# Locate app-owned templates such as hostel/templates/hostel/index.html.
# Without this setting, TemplateView('/') raises TemplateDoesNotExist.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
            ],
        },
    },
]
# Image paths in Oracle are relative to MEDIA_ROOT. Never publicly expose MEDIA_ROOT.
MEDIA_ROOT = BASE_DIR / 'private_media'
HOSTEL_MAX_UPLOAD_MB = int(os.getenv('HOSTEL_MAX_UPLOAD_MB', '5'))
HOSTEL_ALLOWED_ORIGINS = [s.strip() for s in os.getenv('HOSTEL_CORS_ORIGINS', '').split(',') if s.strip()]
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# Django serves the frontend and API from the same origin.
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static_collected'
