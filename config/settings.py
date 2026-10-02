from pathlib import Path

from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-jr_6t*b%2xrl_j7m_xbzhj_0+xps(p2(%re@4vo=1lcfnq$zm_'
DEBUG = True
ALLOWED_HOSTS = ['*']  # development only: list real hostnames in production

INSTALLED_APPS = [
    'unfold',  # must come before django.contrib.admin
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'inventory',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
   # 'django.middleware.csrf.CsrfViewMiddleware',
    'config.middleware.AllowAllOriginsCsrfMiddleware',      # use this instead
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Sign-in
LOGIN_URL = 'landing'
LOGIN_REDIRECT_URL = '/admin/'
ORG_NAME = 'Sare'  # shown on the landing page: change to your organisation's name
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

UNFOLD = {
    "SITE_TITLE": "Uniform Inventory",
    "SITE_HEADER": "Uniform Inventory",
    "DASHBOARD_CALLBACK": "inventory.dashboard.dashboard_callback",
    "SIDEBAR": {
        "show_search": False,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Inventory",
                "separator": False,
                "items": [
                    {"title": "Dashboard", "icon": "dashboard", "link": reverse_lazy("admin:index")},
                    {"title": "Stock items", "icon": "checkroom", "link": reverse_lazy("admin:inventory_stockitem_changelist")},
                    {"title": "Movements", "icon": "swap_horiz", "link": reverse_lazy("admin:inventory_stockmovement_changelist")},
                    {"title": "Uniform types", "icon": "category", "link": reverse_lazy("admin:inventory_uniformtype_changelist")},
                ],
            },
            {
                "title": "Reports",
                "separator": True,
                "items": [
                    {"title": "Stock report", "icon": "inventory_2", "link": reverse_lazy("report", args=["stock"])},
                    {"title": "Movement report", "icon": "receipt_long", "link": reverse_lazy("report", args=["movements"])},
                    {"title": "Who holds what", "icon": "badge", "link": reverse_lazy("report", args=["holdings"])},
                ],
            },
            {
                "title": "Access",
                "separator": True,
                "items": [
                    {
                        "title": "Users", "icon": "person", "link": reverse_lazy("admin:auth_user_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": "Roles", "icon": "group", "link": reverse_lazy("admin:auth_group_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
        ],
    },
}
