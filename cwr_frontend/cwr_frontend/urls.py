"""
URL configuration for cwr_frontend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib.auth.decorators import login_required
from django.urls import re_path, path, include, reverse
from django.views.generic import TemplateView
from django.contrib import admin
from django.http import HttpResponseRedirect

from cwr_frontend.views.WorkflowListView import WorkflowListView
from cwr_frontend.views.WorkflowSubmissionView import WorkflowSubmissionView
from cwr_frontend.views.DatasetListView import DatasetListView
from cwr_frontend.views.DatasetDetailView import DatasetDetailView

def redirect_orcid_login(request):
    next_url = request.GET.get("next", "/")
    orcid_login_url = reverse("orcid_login") + "?process=login&next=" + next_url
    return HttpResponseRedirect(orcid_login_url)

urlpatterns = [
    # browser reload in debug mode
    path("__reload__/", include("django_browser_reload.urls")),
    # list of datasets
    re_path(r'^/?$', DatasetListView.as_view(), name="dataset_list"),
    # regex for dataset ids with forward slash (id=prefix/object_id)
    re_path(r'dataset/(?P<id>[a-z0-9\/]+)', DatasetDetailView.as_view(), name="dataset_detail"),
    re_path('workflows/submit', login_required(WorkflowSubmissionView.as_view()), name="submit_workflow"),
    re_path('workflows', login_required(WorkflowListView.as_view()), name="list_workflows"),
    re_path('imprint', TemplateView.as_view(template_name="imprint.html"), name="imprint"),
    # an ugly hack to serve a placeholder image without using static files
    # replace with actual static file servement!
    path('admin/', admin.site.urls),
    path("accounts/login/", redirect_orcid_login, name="account_login"), # skip login selection page -> always orcid
    path("accounts/", include("allauth.urls")),
]