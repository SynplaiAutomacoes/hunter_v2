from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.messages.storage.fallback import FallbackStorage
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from djmoney.money import Money

from apps.accounts.models import Account
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.core.infrastructure.services.webmania.nfe_emission import build_nfe_payload, download_nfe_preview_document, emit_nfe_request, sync_nfe_emission_response
from apps.customer.forms import QuickCustomerForm
from apps.customer.models import Customer
from apps.customer.views import QuickCustomerCreateView
from apps.finance.forms.nfe_manual import NfeManualEmissionForm, NfeManualItemFormSet, NfeManualQuickProductForm
from apps.finance.models import FiscalEmissionAttempt, NfeEmissionOrigin, NfeItem, NfeManualItemOrigin, NfeRequest, NfeRequestManualItem
from apps.finance.views.nfe_manual import NfeManualEmissionCreateView, NfeManualQuickProductCreateView, NfeManualTransmissionView
from apps.stock.models import StockProduct
from apps.workshops.models.workshops import Workshop


@override_settings(WEBMANIA_NFE_NATUREZA_OPERACAO="Venda de mercadoria", WEBMANIA_AMBIENT="2")
class NfeManualEmissionTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta NF-e manual")
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina NF-e manual",
            cnpj="12.345.678/0001-91",
            phone="+5511988888888",
            address="Rua Manual, 100",
        )
        self.recipient = Customer.objects.create(
            workshop=self.workshop,
            name="Destinatário Manual",
            cpf_or_cnpj="52998224725",
            phone="+5511977777777",
            email="destinatario@example.com",
            cep="01001-000",
            logradouro="Praça da Sé",
            numero=100,
            bairro="Sé",
            cidade="São Paulo",
            estado="SP",
        )
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Produtos manuais")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="MAN-001",
            name="Produto Manual",
            unit=Product.Unit.UND,
            cost_price=Money("25.00", "BRL"),
            selling_price=Money("50.00", "BRL"),
            ncm="87089990",
            origin_cst=Product.OriginCST.NACIONAL,
        )
        self.second_product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="MAN-002",
            name="Segundo Produto Manual",
            unit=Product.Unit.PC,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("25.00", "BRL"),
            ncm="87089990",
            origin_cst=Product.OriginCST.NACIONAL,
        )

    def _create_manual_request(self) -> NfeRequest:
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=None,
            manual_recipient=self.recipient,
            emission_origin=NfeEmissionOrigin.MANUAL,
            current_step=3,
            status="checking_products",
            pricing_slider=0,
            tax_class="REF-MANUAL",
        )
        NfeRequestManualItem.objects.create(
            request=nfe_request,
            product=self.product,
            quantity=Decimal("2.0000"),
            unit_price=Decimal("50.00"),
        )
        return nfe_request

    def test_manual_form_reuses_workshop_customer_and_product(self) -> None:
        form = NfeManualEmissionForm(
            data={
                "recipient": self.recipient.pk,
                "tax_class": "REF-MANUAL",
                "additional_information": "Venda sem OS",
                "confirmation": "on",
            },
            workshop=self.workshop,
            tax_class_choices=[("REF-MANUAL", "REF-MANUAL - Venda")],
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["recipient"], self.recipient)

        item_formset = NfeManualItemFormSet(
            data={
                "items-TOTAL_FORMS": "2",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": self.product.pk,
                "items-0-quantity": "2.0000",
                "items-0-unit_price": "50.00",
                "items-1-product": self.second_product.pk,
                "items-1-quantity": "1.0000",
                "items-1-unit_price": "25.00",
            },
            prefix="items",
            form_kwargs={"workshop": self.workshop},
        )
        self.assertTrue(item_formset.is_valid(), item_formset.errors)
        self.assertEqual(len(item_formset.cleaned_data), 2)

    def test_manual_item_formset_starts_with_one_item_at_quantity_one(self) -> None:
        item_formset = NfeManualItemFormSet(prefix="items", form_kwargs={"workshop": self.workshop})

        self.assertEqual(len(item_formset.forms), 1)
        self.assertEqual(item_formset.forms[0]["quantity"].value(), Decimal("1.0000"))
        self.assertEqual(item_formset.empty_form["quantity"].value(), Decimal("1.0000"))

    def test_manual_item_formset_accepts_removal_when_another_item_remains(self) -> None:
        item_formset = NfeManualItemFormSet(
            data={
                "items-TOTAL_FORMS": "2",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": self.product.pk,
                "items-0-quantity": "1.0000",
                "items-0-unit_price": "50.00",
                "items-0-DELETE": "on",
                "items-1-product": self.second_product.pk,
                "items-1-quantity": "1.0000",
                "items-1-unit_price": "25.00",
            },
            prefix="items",
            form_kwargs={"workshop": self.workshop},
        )

        self.assertTrue(item_formset.is_valid(), item_formset.errors)
        self.assertEqual(len(item_formset.deleted_forms), 1)

    def test_manual_template_renders_multiple_item_controls_and_quick_create_actions(self) -> None:
        form = NfeManualEmissionForm(workshop=self.workshop, tax_class_choices=[("REF-MANUAL", "REF-MANUAL - Venda")])
        item_formset = NfeManualItemFormSet(prefix="items", form_kwargs={"workshop": self.workshop})

        html = render_to_string(
            "finance/nfe_manual_emission_form.html",
            {
                "form": form,
                "item_formset": item_formset,
                "can_add_customer": True,
                "can_add_product": True,
            },
        )

        self.assertIn('id="id_items-TOTAL_FORMS"', html)
        self.assertIn(reverse("customer:quick_create"), html)
        self.assertIn(reverse("finance:emission_manual_quick_product"), html)
        self.assertIn('data-manual-step="1"', html)
        self.assertIn('data-manual-step="2"', html)
        self.assertIn('data-manual-step="3"', html)
        self.assertIn("Destinatário", html)
        self.assertIn("Produtos", html)
        self.assertIn("Revisar e emitir", html)
        self.assertIn("Ver prévia", html)
        self.assertNotIn("Confirmo a emissão desta NF-e", html)
        self.assertIn('hx-target="#manual-nfe-page"', html)
        self.assertEqual(html.count('class="manual-item-row'), 2)
        self.assertIn('data-manual-add-bar="true"', html)
        self.assertGreaterEqual(html.count('class="col-span-6"'), 4)
        self.assertGreaterEqual(html.count('class="col-span-12" data-catalog-product-field'), 2)
        self.assertLess(html.index('id="manual-item-empty-form"'), html.index('data-manual-add-bar="true"'))
        self.assertIn("if (quantity && !quantity.value) quantity.value = '1';", html)
        self.assertIn("formatters.widget.moneyInput", html)
        self.assertIn("R$", html)

    def test_manual_item_form_accepts_brl_unit_price_and_normalizes_backend_value(self) -> None:
        item_formset = NfeManualItemFormSet(
            data={
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": self.product.pk,
                "items-0-quantity": "1",
                "items-0-unit_price": "1.250,50",
            },
            prefix="items",
            form_kwargs={"workshop": self.workshop},
        )

        self.assertTrue(item_formset.is_valid(), item_formset.errors)
        self.assertEqual(item_formset.cleaned_data[0]["unit_price"], Decimal("1250.50"))

    def test_manual_item_form_rejects_fractional_quantity(self) -> None:
        item_formset = NfeManualItemFormSet(
            data={
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": self.product.pk,
                "items-0-quantity": "1.5",
                "items-0-unit_price": "50.00",
            },
            prefix="items",
            form_kwargs={"workshop": self.workshop},
        )

        self.assertFalse(item_formset.is_valid())
        self.assertIn("Informe uma quantidade inteira.", item_formset.forms[0].errors["quantity"])

    def test_manual_progress_saves_step_and_reopens_existing_draft(self) -> None:
        session: dict[str, object] = {}
        request = RequestFactory().post(
            reverse("finance:emission_manual"),
            {"recipient": self.recipient.pk, "_save_progress": "1", "next_step": "2"},
        )
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        request.session = session
        setattr(request, "_messages", FallbackStorage(request))
        view = NfeManualEmissionCreateView()
        view.setup(request)
        view.workshop = self.workshop

        with patch("apps.finance.views.nfe_manual._nfe_tax_class_choices", return_value=[("REF-MANUAL", "Venda")]):
            response = view.post(request)

        self.assertEqual(response.status_code, 200)
        draft = NfeRequest.objects.get(emission_origin=NfeEmissionOrigin.MANUAL)
        self.assertEqual(draft.current_step, 2)
        self.assertEqual(draft.manual_recipient, self.recipient)
        self.assertEqual(session[view._preview_draft_session_key()], draft.pk)

        reload_request = RequestFactory().get(reverse("finance:emission_manual"))
        reload_request.user = request.user
        reload_request.session = session
        reload_view = NfeManualEmissionCreateView()
        reload_view.setup(reload_request)
        reload_view.workshop = self.workshop

        self.assertEqual(reload_view.get_initial()["recipient"], self.recipient.pk)
        self.assertEqual(reload_view.get_context_data(form=NfeManualEmissionForm(workshop=self.workshop))["manual_current_step"], 2)

    def test_new_manual_emission_clears_active_draft_reference_and_redirects_to_canonical_url(self) -> None:
        draft = self._create_manual_request()
        session_key = f"finance.manual_nfe_preview:{self.workshop.pk}:10"
        session = {session_key: draft.pk}
        request = RequestFactory().get(reverse("finance:emission_manual"), {"new": "1"})
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        request.session = session
        view = NfeManualEmissionCreateView()
        view.setup(request)
        view.workshop = self.workshop

        response = view.get(request)

        self.assertRedirects(response, reverse("finance:emission_manual"), fetch_redirect_response=False)
        self.assertNotIn(session_key, session)
        self.assertTrue(NfeRequest.objects.filter(pk=draft.pk).exists())

    def test_manual_stepper_exposes_completed_steps_as_navigation_without_unlocking_future_steps(self) -> None:
        form = NfeManualEmissionForm(workshop=self.workshop, tax_class_choices=[("REF-MANUAL", "REF-MANUAL - Venda")])
        item_formset = NfeManualItemFormSet(prefix="items", form_kwargs={"workshop": self.workshop})

        html = render_to_string(
            "finance/nfe_manual_emission_form.html",
            {
                "form": form,
                "item_formset": item_formset,
                "manual_current_step": 2,
                "manual_max_reached_step": 2,
                "can_add_customer": False,
                "can_add_product": False,
            },
        )

        self.assertIn("data-step-check", html)
        self.assertIn("bg-success/10", html)
        self.assertIn("bg-warning/10", html)
        self.assertIn("indicator.disabled = !accessible", html)
        self.assertIn("if (targetStep <= maxReachedStep) showStep(targetStep)", html)

    def test_manual_template_explains_and_highlights_required_fields(self) -> None:
        form = NfeManualEmissionForm(workshop=self.workshop, tax_class_choices=[("REF-MANUAL", "REF-MANUAL - Venda")])
        item_formset = NfeManualItemFormSet(prefix="items", form_kwargs={"workshop": self.workshop})

        html = render_to_string(
            "finance/nfe_manual_emission_form.html",
            {
                "form": form,
                "item_formset": item_formset,
                "can_add_customer": False,
                "can_add_product": False,
            },
        )

        self.assertIn("Não foi possível avançar para a próxima etapa.", html)
        self.assertIn("data-manual-validation-error", html)
        self.assertIn("input-error", html)
        self.assertIn("border-error", html)
        self.assertIn("Selecione o destinatário da NF-e.", html)
        self.assertIn("Informe uma quantidade inteira maior ou igual a 1.", html)
        self.assertIn("Informe um valor unitário maior que zero.", html)
        self.assertIn("const remainsInvalid = invalidFieldsForStep(currentStep)", html)
        self.assertIn("clearFieldError(field)", html)
        self.assertNotIn("invalidField.reportValidity()", html)

    def test_manual_progress_saves_items_and_restores_step_three(self) -> None:
        draft = self._create_manual_request()
        draft.current_step = 2
        draft.status = "checking_client"
        draft.manual_items.all().delete()
        draft.save(update_fields=["current_step", "status"])
        session = {f"finance.manual_nfe_preview:{self.workshop.pk}:10": draft.pk}
        request = RequestFactory().post(
            reverse("finance:emission_manual"),
            {
                "recipient": self.recipient.pk,
                "_save_progress": "1",
                "next_step": "3",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": self.product.pk,
                "items-0-quantity": "1",
                "items-0-unit_price": "1.250,50",
            },
        )
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        request.session = session
        setattr(request, "_messages", FallbackStorage(request))
        view = NfeManualEmissionCreateView()
        view.setup(request)
        view.workshop = self.workshop

        with patch("apps.finance.views.nfe_manual._nfe_tax_class_choices", return_value=[("REF-MANUAL", "Venda")]):
            response = view.post(request)

        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.current_step, 3)
        item = draft.manual_items.get()
        self.assertEqual(item.quantity, Decimal("1.0000"))
        self.assertEqual(item.unit_price, Decimal("1250.50"))

        draft.tax_class = "REF-MANUAL"
        draft.save(update_fields=["tax_class"])
        with patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"):
            payload = build_nfe_payload(nfe_request=draft)
        self.assertEqual(payload["produtos"][0]["subtotal"], "1250.50")
        self.assertEqual(payload["produtos"][0]["total"], "1250.50")

        reload_request = RequestFactory().get(reverse("finance:emission_manual"))
        reload_request.user = request.user
        reload_request.session = session
        reload_view = NfeManualEmissionCreateView()
        reload_view.setup(reload_request)
        reload_view.workshop = self.workshop
        restored_formset = reload_view.get_item_formset()

        self.assertEqual(restored_formset.forms[0]["product"].value(), self.product.pk)
        self.assertEqual(restored_formset.forms[0]["quantity"].value(), Decimal("1.0000"))
        self.assertEqual(restored_formset.forms[0]["unit_price"].value(), Decimal("1250.50"))

    def test_manual_template_keeps_temporary_product_action_without_catalog_permission(self) -> None:
        form = NfeManualEmissionForm(workshop=self.workshop, tax_class_choices=[("REF-MANUAL", "REF-MANUAL - Venda")])
        item_formset = NfeManualItemFormSet(prefix="items", form_kwargs={"workshop": self.workshop})

        html = render_to_string(
            "finance/nfe_manual_emission_form.html",
            {
                "form": form,
                "item_formset": item_formset,
                "can_add_customer": False,
                "can_add_product": False,
            },
        )

        self.assertNotIn(reverse("customer:quick_create"), html)
        self.assertIn(reverse("finance:emission_manual_quick_product"), html)

    def test_manual_views_use_coherent_existing_permissions(self) -> None:
        self.assertEqual(NfeManualEmissionCreateView.workshop_permission_model, "nferequest")
        self.assertEqual(NfeManualEmissionCreateView.workshop_permission_codename, "view_nferequest")
        self.assertIn(("finance", "nfserequest", "view_nfserequest"), NfeManualEmissionCreateView.workshop_permission_fallbacks)
        self.assertEqual(NfeManualQuickProductCreateView.workshop_permission_model, "nferequest")
        self.assertEqual(NfeManualQuickProductCreateView.workshop_permission_codename, "view_nferequest")
        self.assertIn(("finance", "nfserequest", "view_nfserequest"), NfeManualQuickProductCreateView.workshop_permission_fallbacks)

    def test_manual_view_persists_and_reuses_request_without_transmitting(self) -> None:
        request = RequestFactory().post(
            "/finance/emissao/normal/manual/",
            {
                "recipient": self.recipient.pk,
                "tax_class": "REF-MANUAL",
                "additional_information": "Venda sem OS",
                "confirmation": "on",
                "items-TOTAL_FORMS": "2",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": self.product.pk,
                "items-0-quantity": "2.0000",
                "items-0-unit_price": "50.00",
                "items-1-product": self.second_product.pk,
                "items-1-quantity": "1.0000",
                "items-1-unit_price": "25.00",
            },
        )
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        request.session = {}
        request.htmx = True
        setattr(request, "_messages", FallbackStorage(request))
        form = NfeManualEmissionForm(request.POST, workshop=self.workshop, tax_class_choices=[("REF-MANUAL", "REF-MANUAL - Venda")])
        self.assertTrue(form.is_valid(), form.errors)
        view = NfeManualEmissionCreateView()
        view.setup(request)
        view.workshop = self.workshop

        response = view.form_valid(form)

        nfe_request = NfeRequest.objects.get(emission_origin=NfeEmissionOrigin.MANUAL)
        self.assertIsNone(nfe_request.workorder)
        self.assertEqual(nfe_request.manual_recipient, self.recipient)
        self.assertEqual(set(nfe_request.manual_items.values_list("product_id", flat=True)), {self.product.pk, self.second_product.pk})
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn(reverse("finance:nfe_preview_pdf", kwargs={"pk": nfe_request.pk}), content)
        self.assertIn("data-preview-transmit-form", content)
        self.assertIn(reverse("finance:emission_manual_transmit", kwargs={"pk": nfe_request.pk}), content)
        self.assertIn("Transmitir nota", content)
        self.assertFalse(FiscalEmissionAttempt.objects.filter(request_model="NfeRequest", request_id=nfe_request.pk).exists())
        self.assertFalse(NfeItem.objects.filter(request=nfe_request).exists())

        second_response = view.form_valid(form)

        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(NfeRequest.objects.filter(emission_origin=NfeEmissionOrigin.MANUAL).count(), 1)
        self.assertEqual(nfe_request.pk, request.session[view._preview_draft_session_key()])
        self.assertEqual(NfeRequestManualItem.objects.filter(request=nfe_request).count(), 2)

    def test_quick_customer_is_reused_as_manual_recipient(self) -> None:
        request = RequestFactory().post(
            "/customer/quick-create/",
            {
                "customer_type": "PF",
                "cpf_or_cnpj": "11144477735",
                "name": "Pessoa cadastrada rapidamente",
                "phone": "+5511966666666",
                "email": "rapida@example.com",
                "cep": "01001-000",
                "logradouro": "Praça da Sé",
                "numero": "10",
                "bairro": "Sé",
                "cidade": "São Paulo",
                "estado": "SP",
            },
        )
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        request.htmx = True
        form = QuickCustomerForm(request.POST, workshop=self.workshop)
        self.assertTrue(form.is_valid(), form.errors)
        view = QuickCustomerCreateView()
        view.setup(request)
        view.workshop = self.workshop

        response = view.form_valid(form)

        customer = Customer.objects.get(workshop=self.workshop, cpf_or_cnpj="11144477735")
        self.assertEqual(response.status_code, 204)
        self.assertIn(str(customer.pk), response["HX-Trigger"])

        manual_form = NfeManualEmissionForm(
            data={"recipient": customer.pk, "tax_class": "REF-MANUAL", "confirmation": "on"},
            workshop=self.workshop,
            tax_class_choices=[("REF-MANUAL", "REF-MANUAL - Venda")],
        )
        self.assertTrue(manual_form.is_valid(), manual_form.errors)
        self.assertEqual(manual_form.cleaned_data["recipient"], customer)

    def test_quick_product_view_reuses_catalog_product(self) -> None:
        request = RequestFactory().post(
            "/finance/emissao/normal/manual/produto/cadastro-rapido/",
            {
                "code": "RAP-001",
                "unit": Product.Unit.UND,
                "name": "Produto rápido",
                "group": self.product.group_id,
                "cost_price_0": "12.00",
                "cost_price_1": "BRL",
                "selling_price_0": "24.00",
                "selling_price_1": "BRL",
                "ncm": "87089990",
                "origin_cst": Product.OriginCST.NACIONAL,
                "save_to_catalog": NfeManualQuickProductForm.SAVE_TO_CATALOG,
            },
        )
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        view = NfeManualQuickProductCreateView()
        view.setup(request)
        view.workshop = self.workshop
        with patch("apps.finance.views.nfe_manual.has_workshop_perm", return_value=True):
            form = view.get_form()
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)

        product = Product.objects.get(workshop=self.workshop, code="RAP-001")
        self.assertEqual(response.status_code, 204)
        self.assertIn(str(product.pk), response["HX-Trigger"])

    def test_quick_temporary_product_does_not_create_catalog_or_stock_records(self) -> None:
        product_count = Product.objects.count()
        stock_count = StockProduct.objects.count()
        request = RequestFactory().post(
            "/finance/emissao/normal/manual/produto/cadastro-rapido/",
            {
                "code": "TEMP-001",
                "unit": Product.Unit.PC,
                "name": "Produto exclusivo da nota",
                "selling_price_0": "37.50",
                "selling_price_1": "BRL",
                "ncm": "84212300",
                "cest": "",
                "origin_cst": Product.OriginCST.NACIONAL,
                "save_to_catalog": NfeManualQuickProductForm.USE_ONLY_IN_EMISSION,
            },
        )
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        view = NfeManualQuickProductCreateView()
        view.setup(request)
        view.workshop = self.workshop

        with patch("apps.finance.views.nfe_manual.has_workshop_perm", return_value=False):
            form = view.get_form()
        self.assertTrue(form.is_valid(), form.errors)

        response = view.form_valid(form)
        trigger = json.loads(response["HX-Trigger"])["manualTemporaryProductCreated"]

        self.assertEqual(response.status_code, 204)
        self.assertEqual(Product.objects.count(), product_count)
        self.assertEqual(StockProduct.objects.count(), stock_count)
        self.assertEqual(trigger["snapshot"]["description"], "Produto Exclusivo da Nota")
        self.assertEqual(trigger["snapshot"]["ncm"], "84212300")
        self.assertEqual(trigger["unit_price"], "37.50")

    def test_quick_product_modal_explains_catalog_and_temporary_choices(self) -> None:
        form = NfeManualQuickProductForm(workshop=self.workshop, can_save_to_catalog=True)

        html = render_to_string("finance/partials/nfe_manual_quick_product_modal.html", {"form": form})

        self.assertIn("Salvar este produto no cadastro?", html)
        self.assertIn("Não, usar somente nesta emissão", html)
        self.assertIn("Usar somente nesta NF-e", html)

    def test_quick_product_form_blocks_catalog_save_without_catalog_permission(self) -> None:
        form = NfeManualQuickProductForm(
            data={
                "code": "SEM-PERM",
                "unit": Product.Unit.UND,
                "name": "Produto sem permissão",
                "group": self.product.group_id,
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "ncm": "84212300",
                "origin_cst": Product.OriginCST.NACIONAL,
                "save_to_catalog": NfeManualQuickProductForm.SAVE_TO_CATALOG,
            },
            workshop=self.workshop,
            can_save_to_catalog=False,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("save_to_catalog", form.errors)

    def test_temporary_product_is_persisted_for_preview_and_supported_by_existing_builder(self) -> None:
        snapshot = {
            "description": "Produto exclusivo da nota",
            "code": "TEMP-002",
            "ncm": "84212300",
            "unit": Product.Unit.PC,
            "origin_cst": Product.OriginCST.NACIONAL,
            "cest": "",
        }
        request = RequestFactory().post(
            "/finance/emissao/normal/manual/",
            {
                "recipient": self.recipient.pk,
                "tax_class": "REF-MANUAL",
                "confirmation": "on",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-item_origin": NfeManualItemOrigin.TEMPORARY,
                "items-0-product": "",
                "items-0-fiscal_snapshot": json.dumps(snapshot),
                "items-0-quantity": "2.0000",
                "items-0-unit_price": "37.50",
            },
        )
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        request.session = {}
        request.htmx = True
        setattr(request, "_messages", FallbackStorage(request))
        form = NfeManualEmissionForm(request.POST, workshop=self.workshop, tax_class_choices=[("REF-MANUAL", "REF-MANUAL - Venda")])
        self.assertTrue(form.is_valid(), form.errors)
        view = NfeManualEmissionCreateView()
        view.setup(request)
        view.workshop = self.workshop

        response = view.form_valid(form)

        nfe_request = NfeRequest.objects.get(emission_origin=NfeEmissionOrigin.MANUAL)
        item = nfe_request.manual_items.get()
        self.assertEqual(item.item_origin, NfeManualItemOrigin.TEMPORARY)
        self.assertIsNone(item.product)
        self.assertEqual(item.fiscal_snapshot, snapshot)
        self.assertIn(reverse("finance:nfe_preview_pdf", kwargs={"pk": nfe_request.pk}), response.content.decode())
        self.assertFalse(FiscalEmissionAttempt.objects.filter(request_model="NfeRequest", request_id=nfe_request.pk).exists())

        with patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"):
            payload = build_nfe_payload(nfe_request=nfe_request)

        self.assertEqual(
            payload["produtos"],
            [
                {
                    "nome": "Produto exclusivo da nota",
                    "codigo": "TEMP-002",
                    "ncm": "84212300",
                    "quantidade": "2",
                    "unidade": "PC",
                    "origem": 0,
                    "subtotal": "37.50",
                    "total": "75.00",
                    "classe_imposto": "REF-MANUAL",
                }
            ],
        )

        remote_response = Mock()
        remote_response.status_code = 200
        remote_response.raise_for_status.return_value = None
        remote_response.json.return_value = {"status": "processando", "uuid": str(uuid4()), "modelo": "nfe"}
        with (
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_headers", return_value={}),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_emit_url", return_value="https://example.test/emissao"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_nfe_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_local_ibs_cbs_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.reserve_nfe_request_number"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.requests.post", return_value=remote_response),
        ):
            emit_nfe_request(nfe_request=nfe_request)

        attempt = FiscalEmissionAttempt.objects.get(request_model="NfeRequest", request_id=nfe_request.pk)
        self.assertEqual(attempt.request_payload["produtos"][0]["codigo"], "TEMP-002")

    def test_manual_preview_uses_existing_danfe_preview_without_creating_attempt(self) -> None:
        nfe_request = self._create_manual_request()
        remote_response = Mock()
        remote_response.content = b"%PDF-preview"
        remote_response.headers = {"Content-Type": "application/pdf"}
        remote_response.raise_for_status.return_value = None

        with (
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_headers", return_value={}),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_emit_url", return_value="https://example.test/preview"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_nfe_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_local_ibs_cbs_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.requests.post", return_value=remote_response) as post_mock,
        ):
            document = download_nfe_preview_document(nfe_request=nfe_request)

        self.assertEqual(document.content, b"%PDF-preview")
        self.assertTrue(post_mock.call_args.kwargs["json"]["previa_danfe"])
        self.assertEqual(post_mock.call_args.kwargs["json"]["ID"], str(nfe_request.pk))
        self.assertFalse(FiscalEmissionAttempt.objects.filter(request_model="NfeRequest", request_id=nfe_request.pk).exists())
        nfe_request.refresh_from_db()
        self.assertIsNone(nfe_request.reserved_number)

    def test_manual_request_builds_the_standard_nfe_payload(self) -> None:
        nfe_request = self._create_manual_request()

        with patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"):
            payload = build_nfe_payload(nfe_request=nfe_request)

        self.assertEqual(payload["ID"], str(nfe_request.pk))
        self.assertEqual(payload["cliente"]["cpf"], self.recipient.cpf_or_cnpj)
        self.assertEqual(
            payload["produtos"],
            [
                {
                    "nome": self.product.name,
                    "codigo": self.product.code,
                    "ncm": "87089990",
                    "quantidade": "2",
                    "unidade": "UN",
                    "origem": 0,
                    "subtotal": "50.00",
                    "total": "100.00",
                    "classe_imposto": "REF-MANUAL",
                }
            ],
        )
        self.assertEqual(payload["pedido"]["total"], "100.00")

    def test_manual_request_builds_multiple_items_in_the_standard_payload(self) -> None:
        nfe_request = self._create_manual_request()
        NfeRequestManualItem.objects.create(
            request=nfe_request,
            product=self.second_product,
            quantity=Decimal("1.0000"),
            unit_price=Decimal("25.00"),
        )

        with patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"):
            payload = build_nfe_payload(nfe_request=nfe_request)

        self.assertEqual(len(payload["produtos"]), 2)
        self.assertEqual(payload["produtos"][1]["codigo"], self.second_product.code)
        self.assertEqual(payload["pedido"]["total"], "125.00")

    def test_manual_emission_uses_existing_attempt_and_response_sync(self) -> None:
        nfe_request = self._create_manual_request()
        remote_uuid = str(uuid4())
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "aprovado", "uuid": remote_uuid, "modelo": "nfe", "nfe": "123", "serie": "1"}

        with (
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_headers", return_value={}),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_emit_url", return_value="https://example.test/emissao"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_nfe_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_local_ibs_cbs_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.reserve_nfe_request_number"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.requests.post", return_value=response),
        ):
            response_payload = emit_nfe_request(nfe_request=nfe_request)

        sync_nfe_emission_response(nfe_request=nfe_request, response_payload=response_payload)

        attempt = FiscalEmissionAttempt.objects.get(request_model="NfeRequest", request_id=nfe_request.pk)
        item = NfeItem.objects.get(request=nfe_request, uuid=remote_uuid)
        self.assertEqual(attempt.request_payload["ID"], str(nfe_request.pk))
        self.assertIsNone(item.workorder)
        self.assertEqual(item.request, nfe_request)

    def test_manual_transmission_reuses_preview_request_and_blocks_duplicate_submission(self) -> None:
        nfe_request = self._create_manual_request()
        NfeRequestManualItem.objects.create(
            request=nfe_request,
            product=self.second_product,
            quantity=Decimal("1.0000"),
            unit_price=Decimal("25.00"),
        )
        initial_request_count = NfeRequest.objects.count()
        initial_manual_item_ids = list(nfe_request.manual_items.order_by("pk").values_list("pk", flat=True))
        remote_uuid = str(uuid4())
        remote_response = Mock()
        remote_response.status_code = 200
        remote_response.raise_for_status.return_value = None
        remote_response.json.return_value = {"status": "aprovado", "uuid": remote_uuid, "modelo": "nfe", "nfe": "123", "serie": "1"}
        request = RequestFactory().post(reverse("finance:emission_manual_transmit", kwargs={"pk": nfe_request.pk}))
        request.user = SimpleNamespace(pk=10, is_authenticated=True)
        request.session = {f"finance.manual_nfe_preview:{self.workshop.pk}:10": nfe_request.pk}
        request.htmx = True
        setattr(request, "_messages", FallbackStorage(request))
        view = NfeManualTransmissionView()
        view.setup(request, pk=nfe_request.pk)
        view.workshop = self.workshop

        with (
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_headers", return_value={}),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_emit_url", return_value="https://example.test/emissao"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_nfe_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_local_ibs_cbs_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.reserve_nfe_request_number"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.requests.post", return_value=remote_response) as post_mock,
        ):
            first_response = view.post(request, pk=nfe_request.pk)
            second_response = view.post(request, pk=nfe_request.pk)

        self.assertEqual(first_response.status_code, 204)
        self.assertEqual(first_response["HX-Redirect"], reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk}))
        self.assertEqual(second_response.status_code, 204)
        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(NfeRequest.objects.count(), initial_request_count)
        self.assertEqual(list(nfe_request.manual_items.order_by("pk").values_list("pk", flat=True)), initial_manual_item_ids)
        self.assertEqual(FiscalEmissionAttempt.objects.filter(request_model="NfeRequest", request_id=nfe_request.pk).count(), 1)
        self.assertTrue(NfeItem.objects.filter(request=nfe_request, uuid=remote_uuid).exists())
        self.assertNotIn(f"finance.manual_nfe_preview:{self.workshop.pk}:10", request.session)
