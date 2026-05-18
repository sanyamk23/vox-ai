import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# Sentry — initialise before anything else so it captures startup errors too.
# Opt-in: only active when SENTRY_DSN is set in the environment.
_sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    import logging as _logging

    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[
            DjangoIntegration(),
            LoggingIntegration(
                level=_logging.INFO,        # Capture INFO+ as breadcrumbs
                event_level=_logging.ERROR, # Send ERROR+ as Sentry events
            ),
        ],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,  # Never send PII (phone numbers, names) to Sentry
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
    )

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-dev-only-do-not-use-in-production'
    else:
        raise RuntimeError(
            "DJANGO_SECRET_KEY env var is required when DEBUG=False. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(50))'"
        )

_allowed_hosts_env = os.getenv('ALLOWED_HOSTS', '').strip()
if not _allowed_hosts_env:
    if DEBUG:
        ALLOWED_HOSTS = ['*']
    else:
        raise RuntimeError(
            "ALLOWED_HOSTS env var is required in production. "
            "Set it to your domain(s), e.g. ALLOWED_HOSTS=api.example.com"
        )
else:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(',') if h.strip()]

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv(
        'CSRF_TRUSTED_ORIGINS',
        'https://*.ngrok-free.app,https://*.ngrok.io',
    ).split(',') if o.strip()
]

# When behind ngrok / a reverse proxy that terminates TLS, trust X-Forwarded-Proto
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000          # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'corsheaders',
    'chat',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

_cors_origins = os.getenv('CORS_ALLOWED_ORIGINS', '').strip()
if _cors_origins:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(',') if o.strip()]
    CORS_ALLOW_ALL_ORIGINS = False
elif DEBUG:
    # Dev convenience: wide open when no explicit allow-list is configured.
    CORS_ALLOW_ALL_ORIGINS = True
else:
    # Production without CORS_ALLOWED_ORIGINS set — fail loudly rather than open the API.
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS must be set in production (DEBUG=False). "
        "Example: CORS_ALLOWED_ORIGINS=https://app.yourdomain.com"
    )

ROOT_URLCONF = 'backend.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default='postgres://vox_user:vox_pass@db:5432/vox_db',
        conn_max_age=600,        # Reuse DB connections for 10 min — prevents exhaustion at scale
        conn_health_checks=True, # Verify connection is alive before reuse
    )
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [os.getenv('REDIS_URL', 'redis://redis:6379/0')],
        },
    },
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://redis:6379/0'),
        'KEY_PREFIX': 'vox',
    }
}

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024    # 5 MB — matches _MAX_RESUME_BYTES in views.py
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024    # 6 MB — slight headroom for multipart envelope

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(levelname)-7s %(name)s — %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('LOG_LEVEL', 'INFO').upper(),
    },
    'loggers': {
        'chat': {
            'handlers': ['console'],
            'level': os.getenv('CHAT_LOG_LEVEL', 'INFO').upper(),
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        # twilio.http_client logs each REST request at INFO — quiet it down.
        'twilio.http_client': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
