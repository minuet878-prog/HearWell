from django.apps import AppConfig


class ScreeningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "screening"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from screening.views import sign_in

        user_logged_in.connect(sign_in.forget_pending, dispatch_uid="screening.forget_pending")
