from django.conf import settings
from django.views.generic import TemplateView
from django.shortcuts import render
import requests
from urllib.parse import urlencode


class DatasetDetailView(TemplateView):
    template_name = "dataset_detail.html"

    def get(self, request, **kwargs):
        id = request.GET.get("id", None)

        url = settings.CORDRA["URL"] + "/objects/" + id
        response = requests.get(url, verify=False)
        if response.status_code != 200:
            raise Exception(response.text)

        obj = response.json()

        context = {
            "item_size": 0
        }

        return render(request, self.template_name, context)