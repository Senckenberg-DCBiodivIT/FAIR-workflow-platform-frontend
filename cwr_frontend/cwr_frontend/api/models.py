from django.db import models
from rest_framework_api_key.models import AbstractAPIKey

IDENTIFIER_TYPES = [
    ("orcid", "ORCID"),
    ("doi", "DOI"),
    ("ror", "ROR"),
    ("other", "Other"),
]

ORCID_REGEX = r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{4}"
DOI_REGEX = r"10.\d{4,9}/[-._;()/:A-Z0-9]+"
ROR_REGEX = r"^0[a-hj-km-np-tv-z|0-9]{6}[0-9]{2}$"


class ApiKeyIdentity(models.Model):
    name = models.CharField(max_length=128)
    orcid = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        help_text="DEPRECATED: use id_type + identifier instead",
    )
    id_type = models.CharField(max_length=10, choices=IDENTIFIER_TYPES)
    identifier = models.CharField(max_length=128, null=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        import re

        if self.id_type == "orcid" and not re.fullmatch(
            ORCID_REGEX, self.identifier, re.I
        ):
            raise ValidationError("Invalid ORCID ID")
        if self.id_type == "doi" and not re.fullmatch(DOI_REGEX, self.identifier, re.I):
            raise ValidationError("Invalid DOI")
        if self.id_type == "ror" and not re.fullmatch(ROR_REGEX, self.identifier, re.I):
            raise ValidationError("Invalid ROR")

    def get_url(self):
        if self.id_type == "orcid":
            return f"https://orcid.org/{self.identifier}"
        elif self.id_type == "doi":
            return f"https://doi.org/{self.identifier}"
        elif self.id_type == "ror":
            return f"https://ror.org/{self.identifier}"
        return self.identifier


class CustomAPIKey(AbstractAPIKey):
    identity = models.ForeignKey(
        ApiKeyIdentity,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
