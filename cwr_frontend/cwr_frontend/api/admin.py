from django.contrib import admin
from rest_framework_api_key.admin import APIKeyModelAdmin
from .models import CustomAPIKey

@admin.register(CustomAPIKey)
class OrganizationAPIKeyModelAdmin(APIKeyModelAdmin):
    pass