from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

from apps.core.presentation.navigation import EXTRA_FAVORITABLE_PAGE_DEFINITIONS, NAVBAR_MENU_DEFINITIONS


class NavbarUrlIntegrityTests(SimpleTestCase):
    def test_all_navbar_view_names_reverse(self) -> None:
        failures: list[str] = []

        def collect(entry: dict) -> None:
            view_name = entry.get("view_name")
            if not view_name:
                return
            try:
                reverse(view_name)
            except NoReverseMatch as exc:
                failures.append(f"{entry.get('label')}: {exc}")

        for menu in NAVBAR_MENU_DEFINITIONS:
            collect(menu)
            for item in menu.get("items") or ():
                collect(item)

        for page in EXTRA_FAVORITABLE_PAGE_DEFINITIONS:
            collect(page)

        self.assertEqual(failures, [], msg="; ".join(failures))

    def test_menu_groups_match_production_layout(self) -> None:
        menus = {menu["label"]: menu for menu in NAVBAR_MENU_DEFINITIONS}

        self.assertIn("items", menus["Agendamentos"])
        self.assertEqual(
            [item["label"] for item in menus["Agendamentos"]["items"]],
            ["Criar Agendamento", "Mensagens WhatsApp", "Grupos de Mensagens", "Avaliações"],
        )
        self.assertEqual(
            [item["label"] for item in menus["Estoque"]["items"]],
            [
                "Consulta no Estoque",
                "Cadastro de Produto",
                "Exportar Itens",
                "Importar Itens",
                "Aprovação",
                "Reabastecimento",
                "Relatório",
                "Movimentações",
                "Alertas",
            ],
        )
        self.assertEqual(
            [item["label"] for item in menus["Financeiro"]["items"]],
            [
                "Emitir nota",
                "Central de Notas",
                "Movimentação Financeira",
                "Folha de Pagamento",
                "Apuração de Comissões",
                "Formas de Pagamento",
                "Grupos Financeiros",
                "Gerar DRE",
                "Fluxo de Contas",
            ],
        )
        self.assertEqual(
            [item["label"] for item in menus["Cadastros"]["items"]],
            [
                "Cliente",
                "Colaborador",
                "Fornecedor",
                "Serviço",
                "Kit",
                "Grupo",
                "Checklist",
                "Termos",
                "Planos de Revisão",
                "Perguntas Investigativas",
            ],
        )
        self.assertEqual(
            [item["label"] for item in menus["Gestão"]["items"]],
            [
                "Central de Relatórios",
                "Gerenciar Oficinas",
                "Gerenciar Permissões",
                "Gerenciar Colaboradores",
                "Custo Mensal da Oficina",
                "Gerenciar Sistema",
            ],
        )
