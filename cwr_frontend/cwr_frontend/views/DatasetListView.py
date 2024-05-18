from typing import Any

from django.conf import settings
from django.views.generic import TemplateView
from django.shortcuts import render
import requests
from urllib.parse import urlencode


class DatasetListView(TemplateView):
    template_name = "dataset_list.html"

    def retrieve_items(self) -> dict[str, Any]:
        """ retrieve list of objects from cordra """
        params = {
            "pageNum": 0,
            "pageSize": 100,
            "query": "type:Dataset"
        }

        url = settings.CORDRA["URL"] + "/search"
        response = requests.get(url + "?" + urlencode(params), verify=False)
        if response.status_code != 200:
            raise Exception(response.text)

        return response.json()

    def get(self, request, **kwargs):
        items_response = self.retrieve_items()
        items = items_response["results"]
        items_total_count = items_response["size"]

        # extract base metadata for all items
        items_reduced = []
        for item in items:
            id = item["id"]
            name = None
            description = None
            for graph_element in item["content"]["@graph"]:
                if graph_element["@type"] == "Dataset":
                    name = graph_element["name"]
                    description = graph_element["description"]

            if name is None or id is None:
                raise Exception("Dataset name or id not found for " + item)

            items_reduced.append(dict(
                id=id,
                name=name,
                description=description
            ))

        # render response
        context = {
            "items": items_reduced,
            "total_size": items_total_count
        }

        return render(request, self.template_name, context)
