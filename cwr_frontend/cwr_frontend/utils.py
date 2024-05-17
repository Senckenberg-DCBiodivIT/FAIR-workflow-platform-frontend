from django.http.response import HttpResponse


def add_signpost(response: HttpResponse, postings: dict[str, list]):
    """ inserts signposts as headers in the response
    params:
      result - the response object
      postings - map relating signpost type to list of items.
        items can be strings or tuples relating the url to the link type

    """
    links = []
    for key in postings:
        for item in postings[key]:
            if type(item) == tuple:
                links.append(f"<{item[0]}> ; rel=\"{key}\" ; type=\"{item[1]}\"")
            else:
                links.append(f"<{item}> ; rel=\"{key}\"")
    response["Link"] = " , ".join(links)
