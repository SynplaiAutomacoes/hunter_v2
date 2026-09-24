from __future__ import annotations

from django.http import HttpRequest

from apps.core.presentation.favorites import list_favorite_pages_for_user
from apps.core.presentation.navigation import get_favoritable_pages, get_navbar_menus


def navbar(request: HttpRequest) -> dict[str, object]:
    cached_payload = getattr(request, "_navbar_context_payload", None)
    if cached_payload is not None:
        return cached_payload

    navbar_menus = get_navbar_menus(request)

    payload = {
        "navbar_menus": navbar_menus,
        "navbar_favorites": [],
        "navbar_favorite_urls": set(),
        "unread_count": 0,
        "navbar_home_url": "/core/",
    }
    if not request.user.is_authenticated:
        setattr(request, "_navbar_context_payload", payload)
        return payload

    # HTMX partials do not render the navbar; skip the favorites & unread count queries.
    if getattr(request, "htmx", False):
        setattr(request, "_navbar_context_payload", payload)
        return payload

    from apps.billing.access import get_post_login_url

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

    unread_count = 0
    try:
        from apps.notifications.domain.services.notification_service import NotificationService
        from apps.workshops.util.workshops import get_active_workshop_or_404

        workshop = get_active_workshop_or_404(request)
        unread_count = NotificationService.get_unread_count(user=request.user, workshop=workshop)
    except Exception:
        unread_count = 0

    payload = {
        "navbar_menus": navbar_menus,
        "navbar_favorites": visible_favorites,
        "navbar_favorite_urls": favorite_urls,
        "unread_count": unread_count,
        "navbar_home_url": get_post_login_url(request),
    }
    setattr(request, "_navbar_context_payload", payload)
    return payload
