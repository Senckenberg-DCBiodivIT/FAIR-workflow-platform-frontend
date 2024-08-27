from django import template
from django.conf import settings

register = template.Library()

@register.simple_tag
def cordra_url():
    return settings.CORDRA["URL"]

@register.simple_tag
def argo_url():
    return settings.ARGO_URL

@register.simple_tag
def favicon():
    if settings.DEBUG:
        return settings.STATIC_URL + "favicon_debug.jpeg"
    return settings.STATIC_URL + "favicon.jpeg"
