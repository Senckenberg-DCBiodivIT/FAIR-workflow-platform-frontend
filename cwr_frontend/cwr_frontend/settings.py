"""
Django settings for cwr_frontend project.

Generated by 'django-admin startproject' using Django 5.0.6.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

from pathlib import Path
import os

# read environment variables
import environ
env = environ.Env(
    DEBUG=(bool, False)
)
environ.Env.read_env()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# make frontend available under a sub-path, i.e. /cwr-prototype
FORCE_SCRIPT_NAME = env("FORCE_SCRIPT_NAME", default=None)

# use forwarded hostname if available. This is required to use the correct hostname for reversing urls
# if django is run behind a reverse proxy like nginx
USE_X_FORWARDED_HOST = True

# fix for CSRF issues behind caddy
# see https://stackoverflow.com/questions/72584282/django-caddy-csrf-protection-issues
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# disable trailing slash warning (required to make it work with a forced script name)
SILENCED_SYSTEM_CHECKS = ["urls.W002"]

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY", default='django-insecure-_ycijpb4_p+yk_3i7qtf&et)9yus@+t@#g-l$qbqz+&-qas9px')

CORDRA = {
    "URL": env("CORDRA_URL", default="https://localhost:8443"),
    "PREFIX": env("CORDRA_PREFIX", default="cwr/"),
    "USER": env("CORDRA_USER", default=None),
    "PASSWORD": env("CORDRA_PASSWORD", default=None),
}

WORKFLOW_SERVICE = {
    "URL": env("WORKFLOW_SERVICE_URL", default="http://localhost:8001"),
    "USER": env("WORKFLOW_SERVICE_USER", default="test"),
    "PASSWORD": env("WORKFLOW_SERVICE_PASSWORD", default="test"),
}

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.orcid',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_browser_reload'  # auto reload website in development
]

MIDDLEWARE = [
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
    "allauth.account.middleware.AccountMiddleware",
    "django_browser_reload.middleware.BrowserReloadMiddleware",
    "django_signposting.middleware.SignpostingMiddleware",
]

ROOT_URLCONF = 'cwr_frontend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "cwr_frontend/templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'libraries': {
                'settings_value': 'cwr_frontend.templatetags.settings_value',
            }
        },
    },
]

AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',

    # `allauth` specific authentication methods, such as login by email
    'allauth.account.auth_backends.AuthenticationBackend',
]

SOCIALACCOUNT_ONLY = True
ACCOUNT_EMAIL_VERIFICATION = 'none'

if env("ORCID_CLIENT_ID", default=None) is not None:
    SOCIALACCOUNT_PROVIDERS = {
        'orcid': {
            "BASE_DOMAIN": env("ORCID_BASE_DOMAIN", default="orcid.org"),
            "MEMBER_API": False,  # only need public api for login
            "APP": {
                'client_id': env("ORCID_CLIENT_ID"),
                'secret': env("ORCID_SECRET"),
                'key': ""
            }

        }
    }
    SOCIALACCOUNT_ADAPTER = 'cwr_frontend.orcid_adapter.OrcidAdapter'
    ORCID_ALLOW_LIST = env("ORCID_ALLOW_LIST", default="").split(",")
    ORCID_ADMIN_LIST = env("ORCID_ADMIN_LIST", default="").split(",")

if DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "/var/tmp/django_cache/cwr_frontend",
            "TIMEOUT": 0,
        }
    }
    # Do not send cache-control headers for pages
    CACHE_MIDDLEWARE_SECONDS = 0

WSGI_APPLICATION = 'cwr_frontend.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "cwr_frontend", "static"),
]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
