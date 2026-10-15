from config.settings import *  # noqa: F403

# The manifest storage needs collectstatic (and the frontend build) before {% static %} works;
# tests check Django behaviour, so they use plain storage instead.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
