from django.views.generic import TemplateView
from django.shortcuts import render

from cwr_frontend.cordra.CordraConnector import CordraConnector


class DatasetListView(TemplateView):
    template_name = "dataset_list.html"
    _connector = CordraConnector()

    def get(self, request, **kwargs):
        items_response = self._connector.list_datasets()
        items = items_response["results"]
        items_total_count = items_response["size"]

        # extract base metadata for all items
        items_reduced = []
        for item in items:
            id = item["id"]
            content = item["content"]
            name = content["name"]
            description = content["description"]

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
