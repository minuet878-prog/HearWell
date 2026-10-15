from config.settings import *  # noqa: F403

# The manifest storage needs collectstatic (and the frontend build) before {% static %} works;
# tests check Django behaviour, so they use plain storage instead.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Tests never load debug-toolbar, even when the local .env has DEBUG=True.
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]  # noqa: F405
MIDDLEWARE = [m for m in MIDDLEWARE if not m.startswith("debug_toolbar")]  # noqa: F405
