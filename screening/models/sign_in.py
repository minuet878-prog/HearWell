from django.conf import settings
from django.db import models


class SignInMethodQuerySet(models.QuerySet):
    def for_identity(self, identity):
        """The row of who came back from a provider (an oidc.Identity): by its code only."""
        return self.filter(provider=identity.provider, subject=identity.subject)


class SignInMethod(models.Model):
    # 登入方式 (GLOSSARY.md, spec #505, ADR 0057): a provider and the code it gives this person
    # (`sub`), the only thing an account is known by there; never matched by email. A password is
    # not a row: it is the account's usable password or not. No token is kept.
    class Provider(models.TextChoices):
        GOOGLE = "google", "Google"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sign_in_methods"
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    # Whether the account was made with it (the monthly 保存 count and acceptance 6 read it).
    used_to_register = models.BooleanField(default=False)

    objects = SignInMethodQuerySet.as_manager()

    class Meta:
        verbose_name = verbose_name_plural = "登入方式"
        constraints = (
            models.UniqueConstraint(
                fields=("provider", "subject"), name="sign_in_provider_subject"
            ),
            models.UniqueConstraint(fields=("user", "provider"), name="sign_in_one_per_provider"),
        )

    def __str__(self):
        return f"{self.user} {self.get_provider_display()}"
