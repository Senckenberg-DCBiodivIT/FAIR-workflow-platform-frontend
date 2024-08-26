from django import template
from django.conf import settings

register = template.Library()

@register.simple_tag
def cordra_url():
    return settings.CORDRA["URL"]

@register.simple_tag
def argo_url():
    return settings.ARGO_URL
