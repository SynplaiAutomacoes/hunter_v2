from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.accounts.models import FavoritePage
from apps.core.presentation.navigation import get_favoritable_pages


User = get_user_model()

MAX_FAVORITE_PAGES = 5


class FavoritePageError(Exception):
    pass


class InvalidFavoritePageError(FavoritePageError):
    pass


class FavoritePageLimitError(FavoritePageError):
    pass


def normalize_favorite_url(url: str) -> str:
    raw_url = (url or "").strip()
    if not raw_url:
        raise InvalidFavoritePageError("Nenhuma página foi informada.")

    parsed = urlsplit(raw_url)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        raise InvalidFavoritePageError("A página informada não é válida.")

    return urlunsplit(("", "", parsed.path, parsed.query, ""))


def list_favorite_pages_for_user(*, user: User):
    return FavoritePage.objects.filter(user=user).order_by("position", "pk")


def _resequence_locked_favorites(favorites: list[FavoritePage]) -> None:
    changed_favorites: list[FavoritePage] = []
    for index, favorite in enumerate(favorites, start=1):
        if favorite.position != index:
            favorite.position = index
            changed_favorites.append(favorite)

    if changed_favorites:
        FavoritePage.objects.bulk_update(changed_favorites, ["position"])


def toggle_favorite_page(*, request, user: User, url: str) -> bool:
    normalized_url = normalize_favorite_url(url)
    visible_pages = get_favoritable_pages(request)

    if normalized_url not in visible_pages:
        raise InvalidFavoritePageError("A página informada não pode ser favoritada.")

    with transaction.atomic():
        favorites = list(FavoritePage.objects.select_for_update().filter(user=user).order_by("position", "pk"))
        existing_favorite = next((favorite for favorite in favorites if favorite.url == normalized_url), None)

        if existing_favorite is not None:
            existing_favorite.delete()
            _resequence_locked_favorites([favorite for favorite in favorites if favorite.pk != existing_favorite.pk])
            return False

        if len(favorites) >= MAX_FAVORITE_PAGES:
            raise FavoritePageLimitError("Você pode favoritar no máximo 5 páginas.")

        FavoritePage.objects.create(user=user, url=normalized_url, position=len(favorites) + 1)
        return True


def reorder_favorite_pages(*, user: User, ordered_favorite_ids: list[int]) -> None:
    if not ordered_favorite_ids:
        raise InvalidFavoritePageError("Nenhuma ordem de favoritos foi informada.")

    with transaction.atomic():
        favorites = list(FavoritePage.objects.select_for_update().filter(user=user).order_by("position", "pk"))
        favorites_by_id = {favorite.pk: favorite for favorite in favorites}

        if len(favorites_by_id) != len(favorites):
            raise InvalidFavoritePageError("Não foi possível validar os favoritos informados.")

        unique_ordered_ids = list(dict.fromkeys(ordered_favorite_ids))
        invalid_ids = [favorite_id for favorite_id in unique_ordered_ids if favorite_id not in favorites_by_id]
        if invalid_ids:
            raise InvalidFavoritePageError("Não foi possível validar os favoritos informados.")

        ordered_favorites = [favorites_by_id[favorite_id] for favorite_id in unique_ordered_ids]
        remaining_favorites = [favorite for favorite in favorites if favorite.pk not in set(unique_ordered_ids)]
        _resequence_locked_favorites(ordered_favorites + remaining_favorites)
