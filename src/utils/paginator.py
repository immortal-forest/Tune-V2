import math


def paginate_items(items: list, page: int = 1):
    items_per_page = 10
    pages = math.ceil(len(items) / items_per_page)

    start = (page - 1) * items_per_page
    end = start + items_per_page
    return start, end, pages
