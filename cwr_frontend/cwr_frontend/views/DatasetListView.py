from django.conf import settings
from django.views.generic import TemplateView
from django.shortcuts import render
import requests
from urllib.parse import urlencode


class DatasetListView(TemplateView):
    template_name = "dataset_list.html"

    def get(self, request, **kwargs):
        params = {
            "pageNum": 0,
            "pageSize": 100,
            "query": "type:Dataset"
        }

        url = settings.CORDRA["URL"] + "/search"
        response = requests.get(url + "?" + urlencode(params), verify=False)
        if response.status_code != 200:
            raise Exception(response.text)

        json = response.json()
        items = []
        for item in json["results"]:
            id = item["id"]
            print(id)
            name = None
            description = None
            for graph_element in item["content"]["@graph"]:
                if graph_element["@type"] == "Dataset":
                    name = graph_element["name"]
                    description = graph_element["description"]

            if name is None or id is None:
                raise Exception("Dataset name or id not found for " + item)

            items.append(dict(
                id=id,
                name=name,
                description=description
            ))

        total_size = json["size"]

        context = {
            "items": items,
            "total_size": total_size
        }

        return render(request, self.template_name, context)



