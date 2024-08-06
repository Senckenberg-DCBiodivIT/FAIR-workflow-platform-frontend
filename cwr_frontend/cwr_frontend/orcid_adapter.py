from allauth.core.exceptions import SignupClosedException
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth.models import User


class OrcidAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        orcid = sociallogin.account.uid
        allow_list = settings.ORCID_ALLOW_LIST
        if orcid not in allow_list:
            raise SignupClosedException()
        return True

    def pre_social_login(self, request, sociallogin):
        admin_list = settings.ORCID_ADMIN_LIST
        user = User.objects.get(username=sociallogin.user.username)
        user.is_staff = sociallogin.account.uid in admin_list
        user.is_superuser = sociallogin.account.uid in admin_list
        user.save()

