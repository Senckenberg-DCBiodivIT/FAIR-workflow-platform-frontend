from django.conf import settings
from django.views.generic import TemplateView
from django.shortcuts import render
from django.urls import reverse
from cwr_frontend.utils import add_signpost
import requests


class DatasetDetailView(TemplateView):
    template_name = "dataset_detail.html"

    def get(self, request, **kwargs):
        id = request.GET.get("id", None)

        # get metadata from cordra
        url = settings.CORDRA["URL"] + "/objects/" + id
        response = requests.get(url, verify=False)
        if response.status_code != 200:
            raise Exception(response.text)

        # parse object and dataset
        obj = response.json()
        dataset = next((elem for elem in obj["@graph"] if elem["@type"] == "Dataset"))

        # render content
        context = {
            "name": dataset["name"],
        }
        response =  render(request, self.template_name, context)

        # attach signposting headers
        signposts = {
            "cite-as": [(request.build_absolute_uri(reverse("api", args=[f"objects/{id}"])), "related")],
            "author": [dataset["author"]["@id"]],
            "license": [dataset["license"]["@id"]],
            # TODO items with abs link
            # "item": [item["@id"] for item in dataset["hasPart"]]
            # TODO zipped RO Crate
        }
        add_signpost(response, signposts)

        return response


