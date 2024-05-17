from django.conf import settings
from django.views.generic import TemplateView
from django.shortcuts import render
from django.urls import reverse
from cwr_frontend.utils import add_signpost
import requests
import magic


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

        dataset_author_id = dataset["author"]["@id"]
        author = next((elem for elem in obj["@graph"] if elem["@id"] == dataset_author_id), None)
        author_name = author["name"]

        signposts = {"item": []}

        # render content
        context = {
            "id": id,
            "name": dataset["name"],
            "description": dataset["description"],
            "keywords": dataset["keywords"],
            "datePublished": dataset["datePublished"],
            "author": author_name,
            "author_id": dataset_author_id,
            "images": []
        }

        for part in dataset["hasPart"]:
            part_id = part["@id"]
            item = next((elem for elem in obj["@graph"] if elem["@id"] == part_id), None)
            if item is None:
                continue
            item_id = part_id
            item_type = item["encodingFormat"]
            if (item_type.startswith("image")):
                item_abs_url = request.build_absolute_uri(reverse("api", args=[f"objects/{id}"])) + f"?payload={item_id}"
                signposts["item"].append((item_abs_url, item_type))
                context["images"].append(item_abs_url)

        response = render(request, self.template_name, context)

        # attach signposting headers
        signposts |= {
            "cite-as": [(request.build_absolute_uri(reverse("api", args=[f"objects/{id}"])), "related")],
            "author": [dataset_author_id],
            "license": [dataset["license"]["@id"]],
            # TODO zipped RO Crate
        }
        add_signpost(response, signposts)

        return response


