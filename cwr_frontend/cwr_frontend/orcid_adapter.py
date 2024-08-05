from allauth.core.exceptions import SignupClosedException
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings


class OrcidAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        orcid = sociallogin.account.uid
        allow_list = settings.ORCID_ALLOWLIST
        if orcid not in allow_list:
            raise SignupClosedException()
        return True
