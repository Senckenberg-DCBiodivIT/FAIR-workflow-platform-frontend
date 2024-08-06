import logging

from allauth.core.exceptions import SignupClosedException
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth.models import User


class OrcidAdapter(DefaultSocialAccountAdapter):

    _logger = logging.getLogger(__name__)

    def is_open_for_signup(self, request, sociallogin):
        orcid = sociallogin.account.uid
        allow_list = settings.ORCID_ALLOW_LIST
        if orcid not in allow_list:
            raise SignupClosedException()
        return True

    def pre_social_login(self, request, sociallogin):
        admin_list = settings.ORCID_ADMIN_LIST
        try:
            user = User.objects.get(username=sociallogin.user.username)
            user.is_staff = sociallogin.account.uid in admin_list
            user.is_superuser = sociallogin.account.uid in admin_list
            user.save()
        except User.DoesNotExist:  # ignore on user creation
            pass

    def save_user(self, request, sociallogin, form=None):
        admin_list = settings.ORCID_ADMIN_LIST
        sociallogin.user.is_staff = sociallogin.account.uid in admin_list
        sociallogin.user.is_superuser = sociallogin.account.uid in admin_list
        return super().save_user(request, sociallogin, form)



