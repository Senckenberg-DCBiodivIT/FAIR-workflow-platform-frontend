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
        dataset = next((elem for elem in obj["@graph"] if elem["@type"] == "Dataset"))

        context = {
            "name": dataset["name"],
        }

        result =  render(request, self.template_name, context)

        signposts = {
            "author": [dataset["author"]["@id"]],
            "license": [dataset["license"]["@id"]],
            "item": [item["@id"] for item in dataset["hasPart"]]
        }
        links = []
        for key in signposts:
            for item in signposts[key]:
                links.append(f"<{item}> ; rel=\"{key}\"")
        result["Link"] = " , ".join(links)

        return result