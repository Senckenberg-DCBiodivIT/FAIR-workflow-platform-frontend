from rest_framework_api_key.permissions import BaseHasAPIKey
from .models import CustomAPIKey

class HasCustomAPIKey(BaseHasAPIKey):
    model = CustomAPIKey