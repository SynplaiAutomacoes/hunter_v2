from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.forms import LoginForm


User = get_user_model()


class HoneypotFormTests(TestCase):
    def test_login_rejects_filled_honeypot(self) -> None:
        User.objects.create_user(username="honeypot-user", password="senha123", cpf="12345678901")
        form = LoginForm(
            data={
                "username": "honeypot-user",
                "password": "senha123",
                "website": "http://spam.example",
            }
        )
        self.assertFalse(form.is_valid())

    def test_signup_honeypot_does_not_create_user(self) -> None:
        url = reverse("accounts:register")
        response = self.client.post(
            url,
            data={
                "first_name": "Bot",
                "last_name": "Spam",
                "username": "botspamuser",
                "email": "botspam@example.invalid",
                "cpf": "52998224725",
                "password1": "ComplexPass123!",
                "password2": "ComplexPass123!",
                "website": "http://spam.example",
            },
            HTTP_USER_AGENT="Mozilla/5.0",
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username="botspamuser").exists())
