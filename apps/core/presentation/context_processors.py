from __future__ import annotations

from django.http import HttpRequest

from apps.core.presentation.favorites import list_favorite_pages_for_user
from apps.core.presentation.navigation import get_favoritable_pages, get_navbar_menus


def navbar(request: HttpRequest) -> dict[str, object]:
    cached_payload = getattr(request, "_navbar_context_payload", None)
    if cached_payload is not None:
        return cached_payload

    navbar_menus = get_navbar_menus(request)

    if not request.user.is_authenticated:
        payload = {
            "navbar_menus": navbar_menus,
            "navbar_favorites": [],
            "navbar_favorite_urls": set(),
        }
        setattr(request, "_navbar_context_payload", payload)
        return payload

    # HTMX partials do not render the navbar; skip the favorites query.
    if getattr(request, "htmx", False):
        payload = {
            "navbar_menus": navbar_menus,
            "navbar_favorites": [],
            "navbar_favorite_urls": set(),
        }
        setattr(request, "_navbar_context_payload", payload)
        return payload

    all_favorites = list(list_favorite_pages_for_user(user=request.user))
    favorite_urls = {favorite.url for favorite in all_favorites}
    visible_pages = get_favoritable_pages(request)
    visible_favorites = [
        {
            "id": favorite.pk,
            "href": favorite.url,
            "label": visible_pages[favorite.url]["label"],
        }
        for favorite in all_favorites
        if favorite.url in visible_pages
    ]

    payload = {
        "navbar_menus": navbar_menus,
        "navbar_favorites": visible_favorites,
        "navbar_favorite_urls": favorite_urls,
    }
    setattr(request, "_navbar_context_payload", payload)
    return payload
