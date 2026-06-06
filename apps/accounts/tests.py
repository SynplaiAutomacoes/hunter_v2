from __future__ import annotations

import json
from typing import Any

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import FavoritePage
from apps.core.presentation.context_processors import navbar
from apps.workshops.tests import create_director_user_with_workshop


class FavoritePageViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user, self.workshop = create_director_user_with_workshop(suffix=41)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.favorite_urls = [
            reverse("customer:customer_list"),
            reverse("collaborators:collaborator_list"),
            reverse("stock:transfer"),
            reverse("finance:issued_documents_list"),
            reverse("finance:reports_home"),
            reverse("workshops:list"),
        ]
        self.page_favorite_url = reverse("budget:budget_create")
        self.extra_favorite_urls = [
            reverse("budget:budget_create"),
            reverse("customer:customer_create"),
            reverse("collaborators:collaborator_create"),
            reverse("suppliers:supplier_create"),
            reverse("catalog:product_create"),
            reverse("catalog:services_create"),
            reverse("catalog:kits_create"),
            reverse("catalog:group_create"),
            reverse("checklist:checklist_create"),
            f"{reverse('scheduling:appointment_calendar')}?open=create",
            reverse("stock:import"),
            reverse("finance:financial_movement_create"),
        ]
        self.non_favoritable_urls = [
            reverse("budget:budget_list"),
            reverse("workorder:workorder_list"),
            reverse("scheduling:appointment_calendar"),
        ]

    def _toggle(self, url: str):
        return self.client.post(reverse("core:favorite_page_toggle"), {"url": url}, HTTP_HX_REQUEST="true")

    def test_toggle_view_adds_favorite_and_requests_refresh(self) -> None:
        response = self._toggle(self.favorite_urls[0])

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        favorite = FavoritePage.objects.get(user=self.user, url=self.favorite_urls[0])
        self.assertEqual(favorite.position, 1)

    def test_toggle_view_removes_favorite_and_resequences_remaining_items(self) -> None:
        self._toggle(self.favorite_urls[0])
        self._toggle(self.favorite_urls[1])

        response = self._toggle(self.favorite_urls[0])

        self.assertEqual(response.status_code, 204)
        self.assertFalse(FavoritePage.objects.filter(user=self.user, url=self.favorite_urls[0]).exists())
        remaining_favorite = FavoritePage.objects.get(user=self.user, url=self.favorite_urls[1])
        self.assertEqual(remaining_favorite.position, 1)

    def test_toggle_view_blocks_sixth_favorite_with_modal_event(self) -> None:
        for url in self.favorite_urls[:5]:
            response = self._toggle(url)
            self.assertEqual(response.status_code, 204)

        response = self._toggle(self.favorite_urls[5])

        self.assertEqual(response.status_code, 204)
        trigger_payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger_payload["favoritePagesLimitReached"]["title"], "Limite de favoritos atingido")
        self.assertEqual(FavoritePage.objects.filter(user=self.user).count(), 5)
        self.assertFalse(FavoritePage.objects.filter(user=self.user, url=self.favorite_urls[5]).exists())

    def test_toggle_view_rejects_invalid_url(self) -> None:
        response = self._toggle("/pagina-invalida/")

        self.assertEqual(response.status_code, 400)
        trigger_payload = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(trigger_payload["showToast"]["type"], "warning")
        self.assertFalse(FavoritePage.objects.filter(user=self.user).exists())

    def test_toggle_view_rejects_non_favoritable_navbar_pages(self) -> None:
        for url in self.non_favoritable_urls:
            response = self._toggle(url)

            self.assertEqual(response.status_code, 400)

        self.assertFalse(FavoritePage.objects.filter(user=self.user).exists())

    def test_toggle_view_accepts_registered_non_navbar_pages(self) -> None:
        for url in self.extra_favorite_urls:
            with self.subTest(url=url):
                response = self._toggle(url)

                self.assertEqual(response.status_code, 204)
                favorite = FavoritePage.objects.get(user=self.user, url=url)
                self.assertEqual(favorite.position, 1)

                FavoritePage.objects.filter(user=self.user).delete()

    def test_toggle_view_rejects_querystring_variant_of_page_level_favorite(self) -> None:
        response = self._toggle(f"{self.page_favorite_url}?step=2&pk=17")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(FavoritePage.objects.filter(user=self.user, url=self.page_favorite_url).exists())

    def test_reorder_view_updates_positions_using_sent_order(self) -> None:
        for url in self.favorite_urls[:3]:
            self._toggle(url)

        favorites = list(FavoritePage.objects.filter(user=self.user).order_by("position", "pk"))
        response = self.client.post(
            reverse("core:favorite_page_reorder"),
            {"favorite_ids": [favorites[2].pk, favorites[0].pk, favorites[1].pk]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        reordered_urls = list(FavoritePage.objects.filter(user=self.user).order_by("position", "pk").values_list("url", flat=True))
        self.assertEqual(reordered_urls, [self.favorite_urls[2], self.favorite_urls[0], self.favorite_urls[1]])

    def test_navbar_context_processor_exposes_visible_favorites_in_saved_order(self) -> None:
        for url in [self.favorite_urls[0], self.page_favorite_url, self.favorite_urls[1]]:
            self._toggle(url)

        request = self.factory.get("/")
        request.user = self.user
        request.session = self.client.session

        payload: dict[str, Any] = navbar(request)
        visible_favorites: list[dict[str, Any]] = payload.get("navbar_favorites") or []
        favorite_urls: set[str] = payload.get("navbar_favorite_urls") or set()

        self.assertEqual([favorite["href"] for favorite in visible_favorites], [self.favorite_urls[0], self.page_favorite_url, self.favorite_urls[1]])
        self.assertIn(self.favorite_urls[0], favorite_urls)
        self.assertIn(self.page_favorite_url, favorite_urls)
