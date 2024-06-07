from datetime import datetime

from django.views.generic import TemplateView
from django.shortcuts import render
import logging

from cwr_frontend.cordra.CordraConnector import CordraConnector


class DatasetListView(TemplateView):
    template_name = "dataset_list.html"
    _connector = CordraConnector()

    _logger = logging.getLogger(__name__)

    def get(self, request, **kwargs):
        items_response = self._connector.list_datasets()
        items = items_response["results"]
        items_total_count = items_response["size"]

        # extract base metadata for all items
        items_reduced = []
        for item in items:
            id = item["id"]
            if id is None:
                raise Exception(f"Dataset has no valid id for {item}")

            content = item["content"]
            if "name" in content:
                name = content["name"]
            else:
                self._logger.warning(f"Dataset has no valid name for {item}")
                name = id

            items_reduced.append(dict(
                id=id,
                name=name,
                description=content["description"],
                file_count=len(content["hasPart"]),
                date_modified=datetime.strptime(content["dateModified"], "%Y-%m-%dT%H:%M:%S.%fZ")
            ))

        # render response
        context = {
            "items": items_reduced,
            "total_size": items_total_count
        }

        return render(request, self.template_name, context)
