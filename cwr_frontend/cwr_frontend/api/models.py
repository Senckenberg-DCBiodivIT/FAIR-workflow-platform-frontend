from django.db import models
from django.core.validators import RegexValidator
from rest_framework_api_key.models import AbstractAPIKey, BaseAPIKeyManager

class ApiKeyIdentity(models.Model):
    name = models.CharField(max_length=128)

    orcid_validator = RegexValidator(r"[0-9A-Z]{4}\-[0-9A-Z]{4}\-[0-9A-Z]{4}\-[0-9A-Z]{4}", message="Enter a valid ORCID ID")
    orcid = models.CharField(max_length=128, validators=[orcid_validator])
       
class CustomAPIKey(AbstractAPIKey):
    identity = models.ForeignKey(
        ApiKeyIdentity,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    objects: BaseAPIKeyManager = BaseAPIKeyManager()