from django.core.paginator import Paginator


def build_query_string(request, *, exclude_keys=None):
    query = request.GET.copy()
    ignored_keys = set(exclude_keys or ())
    ignored_keys.add("page")

    for key in ignored_keys:
        query.pop(key, None)

    return query.urlencode()


def paginate_collection(request, collection, *, per_page=12):
    paginator = Paginator(collection, per_page)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    return page_obj
