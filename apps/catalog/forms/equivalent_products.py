from __future__ import annotations

import json
from urllib.parse import quote

from django.db.models import QuerySet
from django.template.loader import render_to_string

from crispy_forms.layout import Div, Field, HTML

from apps.catalog.equivalent_products import get_equivalent_products_queryset, serialize_equivalent_product, serialize_equivalent_products
from apps.catalog.models.products import Product


class EquivalentProductsFormMixin:
    def _get_equivalent_ignore_id(self) -> int | None:
        instance = getattr(self, "instance", None)
        return int(instance.pk) if instance and instance.pk else None

    def _get_bound_equivalent_search_value(self) -> str:
        if not getattr(self, "is_bound", False):
            return ""
        form_data = getattr(self, "data", None)
        if form_data is None or not hasattr(form_data, "get"):
            return ""
        return str(form_data.get("equivalent_search", "") or "").strip()

    def _get_selected_equivalent_ids_from_data(self) -> list[str]:
        if not getattr(self, "is_bound", False):
            return []
        form_data = getattr(self, "data", None)
        if form_data is None or not hasattr(form_data, "getlist"):
            return []
        return [value for value in form_data.getlist("equivalent_parts") if str(value).isdigit()]

    def _build_initial_equivalent_products(self) -> list[dict[str, str]]:
        selected_ids = self._get_selected_equivalent_ids_from_data()
        workshop = getattr(self, "workshop", None)
        instance = getattr(self, "instance", None)

        if getattr(self, "is_bound", False):
            if not selected_ids or not workshop:
                return []

            products_by_id = {
                str(product.pk): serialize_equivalent_product(product)
                for product in get_equivalent_products_queryset(
                    workshop=workshop,
                    ignore_product_id=self._get_equivalent_ignore_id(),
                ).filter(pk__in=[int(value) for value in selected_ids])
            }
            return [products_by_id[value] for value in selected_ids if value in products_by_id]

        if not instance or not instance.pk:
            return []

        return serialize_equivalent_products(instance.equivalent_parts.only("id", "code", "name", "brand").order_by("name", "code"))

    def _render_equivalent_product_rows(self) -> str:
        products: QuerySet[Product] = Product.objects.none()
        workshop = getattr(self, "workshop", None)
        if workshop:
            products = get_equivalent_products_queryset(
                workshop=workshop,
                search_value=self._get_bound_equivalent_search_value(),
                ignore_product_id=self._get_equivalent_ignore_id(),
            )

        return render_to_string("products/partials/equivalent_product_rows.html", {"products": products})

    def build_equivalent_products_section(self, *, search_url: str, sync_url: str = ""):
        initial_equivalents = self._build_initial_equivalent_products()
        equivalents_json = json.dumps(initial_equivalents)
        rendered_rows = self._render_equivalent_product_rows()
        instance = getattr(self, "instance", None)
        instance_pk = instance.pk if instance and instance.pk else None
        can_persist_equivalent_products = bool(instance_pk and sync_url)
        save_button_html = ""
        if can_persist_equivalent_products:
            save_button_html = """
                <button
                    type=\"button\"
                    class=\"btn btn-primary w-full sm:w-auto\"
                    :disabled=\"isPersistingEquivalentProducts || !hasPendingEquivalentChanges()\"
                    @click=\"applyEquivalentProducts()\"
                >
                    <span x-show=\"!isPersistingEquivalentProducts\">Salvar Produtos Equivalentes</span>
                    <span x-show=\"isPersistingEquivalentProducts\">Salvando...</span>
                </button>
            """
        encoded_sync_url = quote(sync_url, safe="/:?=&")

        return Div(
            Div(
                Field(
                    "equivalent_search",
                    css_class="input-theme border-none bg-base-100",
                    wrapper_class="w-full !bg-transparent",
                    autocomplete="off",
                    placeholder="Buscar por código, nome ou marca...",
                    hx_get=search_url,
                    hx_trigger="keyup changed delay:300ms, search",
                    hx_target="#equivalent-products-items",
                    hx_swap="innerHTML",
                    id="equivalent-search-input",
                    type="search",
                    hx_vals=json.dumps({"ignore_id": instance_pk}) if instance_pk else "{}",
                ),
                css_class="w-full mb-4",
            ),
            HTML(
                f"""
                <div class=\"overflow-hidden rounded-box border border-base-300 bg-base-100\">
                    <div class=\"max-h-[26rem] overflow-auto\">
                        <table class=\"table table-sm table-zebra w-full\">
                            <thead class=\"sticky top-0 z-10 bg-base-100\">
                                <tr>
                                    <th class=\"w-14 text-center\">Selecionar</th>
                                    <th class=\"whitespace-nowrap\">Código</th>
                                    <th>Produto</th>
                                    <th>Marca</th>
                                    <th class=\"w-28 pr-4 text-right sm:pr-5\">Ação</th>
                                </tr>
                            </thead>
                            <tbody id=\"equivalent-products-items\">{rendered_rows}</tbody>
                        </table>
                    </div>

                    <div class=\"flex flex-col gap-3 border-t border-base-300 bg-base-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between\">
                        <div class=\"space-y-1\">
                            <p class=\"text-sm font-medium text-base-content/80\" x-text=\"`${{pendingEquivalentProducts.length}} produto(s) marcado(s) na tabela.`\"></p>
                            <p
                                class=\"text-xs\"
                                :class=\"equivalentHelperTextClass()\"
                                x-text=\"equivalentHelperText()\"
                            ></p>
                        </div>

                        {save_button_html}
                    </div>
                </div>
                """
            ),
            HTML(
                """
                <select name="equivalent_parts" multiple class="hidden">
                    <template x-for="item in submittedEquivalentProducts()" :key="'equivalent-option-' + item.id">
                        <option :value="item.id" selected></option>
                    </template>
                </select>
                """
            ),
            **{
                "x-data": f"""{{
                    appliedEquivalentProducts: {equivalents_json},
                    pendingEquivalentProducts: {equivalents_json},
                    canPersistEquivalentProducts: {str(can_persist_equivalent_products).lower()},
                    equivalentSyncUrl: '{encoded_sync_url}',
                    isPersistingEquivalentProducts: false,
                    init() {{
                        this.appliedEquivalentProducts = this.normalizeEquivalentProducts(this.appliedEquivalentProducts);
                        this.pendingEquivalentProducts = this.normalizeEquivalentProducts(this.pendingEquivalentProducts);
                    }},
                    normalizeEquivalentProducts(items) {{
                        return (items || []).map((item) => ({{
                            id: String(item.id),
                            code: item.code || '',
                            name: item.name || '',
                            brand: item.brand || '',
                        }}));
                    }},
                    equivalentSelectionSignature(items) {{
                        return JSON.stringify(this.normalizeEquivalentProducts(items).map((item) => item.id).sort());
                    }},
                    submittedEquivalentProducts() {{
                        return this.canPersistEquivalentProducts ? this.appliedEquivalentProducts : this.pendingEquivalentProducts;
                    }},
                    hasPendingEquivalentChanges() {{
                        return this.equivalentSelectionSignature(this.appliedEquivalentProducts) !== this.equivalentSelectionSignature(this.pendingEquivalentProducts);
                    }},
                    equivalentHelperText() {{
                        if (!this.canPersistEquivalentProducts) {{
                            return 'Os produtos equivalentes serão salvos quando você salvar o produto.';
                        }}

                        if (this.hasPendingEquivalentChanges()) {{
                            return 'Existem alterações pendentes. Clique em salvar produtos equivalentes para persistir no banco de dados.';
                        }}

                        return 'Seleção sincronizada com o banco de dados.';
                    }},
                    equivalentHelperTextClass() {{
                        if (!this.canPersistEquivalentProducts) {{
                            return 'text-base-content/60';
                        }}

                        return this.hasPendingEquivalentChanges() ? 'text-warning' : 'text-base-content/60';
                    }},
                    isAppliedEquivalent(productId) {{
                        return this.appliedEquivalentProducts.some((item) => item.id === String(productId));
                    }},
                    isPendingEquivalent(productId) {{
                        return this.pendingEquivalentProducts.some((item) => item.id === String(productId));
                    }},
                    getCsrfToken() {{
                        const csrfField = document.querySelector('input[name="csrfmiddlewaretoken"]');
                        return csrfField ? csrfField.value : '';
                    }},
                    showToast(message, type = 'warning') {{
                        document.body.dispatchEvent(new CustomEvent('showToast', {{
                            detail: {{ message, type }},
                        }}));
                    }},
                    async syncEquivalentProducts(selectedItems, successMessage, pendingItemsOnSuccess = null) {{
                        if (!this.canPersistEquivalentProducts || !this.equivalentSyncUrl) {{
                            return this.normalizeEquivalentProducts(selectedItems);
                        }}

                        this.isPersistingEquivalentProducts = true;

                        try {{
                            const response = await fetch(this.equivalentSyncUrl, {{
                                method: 'POST',
                                headers: {{
                                    'Content-Type': 'application/json',
                                    'X-CSRFToken': this.getCsrfToken(),
                                    'X-Requested-With': 'XMLHttpRequest',
                                }},
                                credentials: 'same-origin',
                                body: JSON.stringify({{
                                    equivalent_ids: this.normalizeEquivalentProducts(selectedItems).map((item) => item.id),
                                }}),
                            }});

                            const payload = await response.json().catch(() => ({{}}));
                            if (!response.ok) {{
                                throw new Error(payload.message || 'Não foi possível salvar os produtos equivalentes.');
                            }}

                            const normalizedEquivalents = this.normalizeEquivalentProducts(payload.equivalents || []);
                            this.appliedEquivalentProducts = normalizedEquivalents;
                            this.pendingEquivalentProducts = this.normalizeEquivalentProducts(pendingItemsOnSuccess ?? normalizedEquivalents);
                            this.showToast(successMessage || payload.message || 'Produtos equivalentes salvos com sucesso.', payload.type || 'success');
                            return normalizedEquivalents;
                        }} finally {{
                            this.isPersistingEquivalentProducts = false;
                        }}
                    }},
                    togglePendingEquivalent(product, checked) {{
                        const normalizedProduct = {{
                            id: String(product.id),
                            code: product.code || '',
                            name: product.name || '',
                            brand: product.brand || '',
                        }};

                        if (checked) {{
                            if (!this.isPendingEquivalent(normalizedProduct.id)) {{
                                this.pendingEquivalentProducts.push(normalizedProduct);
                            }}
                            return;
                        }}

                        this.pendingEquivalentProducts = this.pendingEquivalentProducts.filter((item) => item.id !== normalizedProduct.id);
                    }},
                    async removeAppliedEquivalent(productId) {{
                        const normalizedId = String(productId);
                        const previousAppliedEquivalentProducts = this.normalizeEquivalentProducts(this.appliedEquivalentProducts);
                        const previousPendingEquivalentProducts = this.normalizeEquivalentProducts(this.pendingEquivalentProducts);
                        const nextAppliedEquivalentProducts = previousAppliedEquivalentProducts.filter((item) => item.id !== normalizedId);
                        const nextPendingEquivalentProducts = previousPendingEquivalentProducts.filter((item) => item.id !== normalizedId);

                        this.appliedEquivalentProducts = nextAppliedEquivalentProducts;
                        this.pendingEquivalentProducts = nextPendingEquivalentProducts;

                        if (!this.canPersistEquivalentProducts) {{
                            return;
                        }}

                        try {{
                            await this.syncEquivalentProducts(nextAppliedEquivalentProducts, 'Produto equivalente removido com sucesso.', nextPendingEquivalentProducts);
                        }} catch (error) {{
                            this.appliedEquivalentProducts = previousAppliedEquivalentProducts;
                            this.pendingEquivalentProducts = previousPendingEquivalentProducts;
                            this.showToast(error.message || 'Não foi possível remover o produto equivalente.', 'error');
                        }}
                    }},
                    async applyEquivalentProducts() {{
                        if (!this.canPersistEquivalentProducts) {{
                            return;
                        }}

                        if (!this.hasPendingEquivalentChanges()) {{
                            return;
                        }}

                        try {{
                            await this.syncEquivalentProducts(this.pendingEquivalentProducts, 'Produtos equivalentes salvos com sucesso.');
                        }} catch (error) {{
                            this.showToast(error.message || 'Não foi possível salvar os produtos equivalentes.', 'error');
                        }}
                    }},
                }}""",
                "id": "equivalents-manager",
            },
            css_class="col-span-12 p-4 bg-base-300 rounded-box",
        )
