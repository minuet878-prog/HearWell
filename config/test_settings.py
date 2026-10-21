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


def worktree_test_database(base_dir, database_name):
    """A worktree's own test database name, so its tests can run beside the main folder's."""
    if base_dir.parent.name == "worktrees" and base_dir.parent.parent.name == ".claude":
        return f"test_{database_name}_{base_dir.name}"
    return None


if name := worktree_test_database(BASE_DIR, DATABASES["default"]["NAME"]):  # noqa: F405
    DATABASES["default"]["TEST"] = {"NAME": name}  # noqa: F405
