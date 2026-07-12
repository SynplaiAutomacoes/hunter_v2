import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from djmoney.money import Money

from apps.accounts.models import Account, User
from apps.budget.models import Budget, BudgetItem, BudgetStatus, BudgetType
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.customer.models import Customer, Vehicle
from apps.iam.models import WorkshopRole
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


class Command(BaseCommand):
    help = "Seeds the database with demo data for Hunter V2"

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding demo data...")

        # 1. Create Account Owner
        owner, created = User.objects.get_or_create(
            username="admin@hunter.com",
            defaults={
                "email": "admin@hunter.com",
                "is_staff": True,
                "is_superuser": True,
                "is_account_owner": True,
                "cpf": "12345678901",
            },
        )
        if created:
            owner.set_password("admin123")
            owner.save()
            self.stdout.write(f"Created owner: {owner.username}")

        # 2. Create Account
        account, _ = Account.objects.get_or_create(
            name="Hunter Demo Account",
            defaults={"owner": owner},
        )
        owner.account = account
        owner.save(update_fields=["account"])

        # 3. Create Workshop
        workshop, _ = Workshop.objects.get_or_create(
            cnpj="12345678000199",
            defaults={
                "account": account,
                "name": "Oficina Hunter Demo",
                "phone": "+5511999999999",
                "address": "Rua das Oficinas, 123 - São Paulo/SP",
            },
        )

        # 4. Create Role and Member
        role, _ = WorkshopRole.objects.get_or_create(
            account=account,
            name="Administrador",
            defaults={"is_system": True, "is_editable": False},
        )

        WorkshopMember.objects.get_or_create(
            user=owner,
            workshop=workshop,
            defaults={"role": role},
        )

        # 5. Create Collaborator
        collaborator, _ = WorkshopCollaborator.objects.get_or_create(
            workshop=workshop,
            cpf="12345678901",
            defaults={
                "user": owner,
                "name": "Alan Souza",
                "birth_date": date(1990, 1, 1),
                "admission_date": date(2020, 1, 1),
                "collaborator_type": WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
                "salary": Money(5000, "BRL"),
                "receives_commission": True,
                "commission_percentage": Decimal("0.05"),
                "is_active": True,
                "system_access": True,
            },
        )

        # 6. Catalog Group
        group, _ = CatalogGroup.objects.get_or_create(
            workshop=workshop,
            name="Geral",
        )

        # 7. Products
        products_data = [
            ("P001", "Filtro de Óleo", 30, 60),
            ("P002", "Pastilha de Freio", 120, 250),
            ("P003", "Óleo Sintético 5W30", 40, 85),
            ("P004", "Disco de Freio", 200, 450),
        ]
        products = []
        for code, name, cost, sell in products_data:
            p, _ = Product.objects.get_or_create(
                workshop=workshop,
                code=code,
                defaults={
                    "name": name,
                    "unit": Product.Unit.PC,
                    "group": group,
                    "cost_price": Money(cost, "BRL"),
                    "selling_price": Money(sell, "BRL"),
                    "ncm": "84212300",
                },
            )
            products.append(p)

        # 8. Services
        services_data = [
            ("Troca de Óleo", "Troca de óleo e filtro", timedelta(minutes=30), 50),
            ("Manutenção de Freios", "Troca de pastilhas e discos", timedelta(hours=1, minutes=30), 150),
            ("Alinhamento e Balanceamento", "Serviço completo", timedelta(hours=1), 120),
        ]
        services = []
        for name, desc, duration, sell in services_data:
            s, _ = Service.objects.get_or_create(
                workshop=workshop,
                name=name,
                defaults={
                    "description": desc,
                    "duration": duration,
                    "selling_price": Money(sell, "BRL"),
                },
            )
            services.append(s)

        # 9. Customers and Vehicles
        customers_data = [
            ("João Silva", "11122233344", "joao@example.com", "ABC1D23", "Toyota", "Corolla", 2020),
            ("Maria Oliveira", "55566677788", "maria@example.com", "XYZ9A87", "Honda", "Civic", 2022),
        ]
        
        for name, doc, email, plate, brand, model, year in customers_data:
            customer, _ = Customer.objects.get_or_create(
                workshop=workshop,
                cpf_or_cnpj=doc,
                defaults={
                    "name": name,
                    "email": email,
                },
            )
            Vehicle.objects.get_or_create(
                workshop=workshop,
                plate=plate,
                defaults={
                    "customer": customer,
                    "brand": brand,
                    "model": model,
                    "year_fabrication": str(year),
                    "year_model": str(year),
                },
            )

        # 10. Budgets and WorkOrders
        # Budget 1: Standard Sale
        c1 = Customer.objects.get(cpf_or_cnpj="11122233344", workshop=workshop)
        v1 = Vehicle.objects.get(plate="ABC1D23", workshop=workshop)
        
        b1, _ = Budget.objects.get_or_create(
            workshop=workshop,
            customer=c1,
            vehicle=v1,
            status=BudgetStatus.APPROVED,
            defaults={
                "entry_date": timezone.now().date(),
                "budget_type": BudgetType.SALE,
            },
        )
        if b1.items.count() == 0:
            BudgetItem.objects.create(
                workshop=workshop, budget=b1, product=products[0], quantity=1,
                product_cost_price=products[0].cost_price, product_selling_price=products[0].selling_price
            )
            BudgetItem.objects.create(
                workshop=workshop, budget=b1, service=services[0], quantity=1,
                service_cost_price=Money(10, "BRL"), service_selling_price=services[0].selling_price
            )
        
        # Ensure WorkOrder for Budget 1
        WorkOrder.objects.get_or_create(
            budget=b1,
            defaults={"workshop": workshop, "status": WorkOrderStatus.DRAFT},
        )

        # Budget 2: Warranty (Testing the new fix)
        c2 = Customer.objects.get(cpf_or_cnpj="55566677788", workshop=workshop)
        v2 = Vehicle.objects.get(plate="XYZ9A87", workshop=workshop)
        
        b2, _ = Budget.objects.get_or_create(
            workshop=workshop,
            customer=c2,
            vehicle=v2,
            status=BudgetStatus.APPROVED,
            defaults={
                "entry_date": timezone.now().date(),
                "budget_type": BudgetType.WARRANTY,
            },
        )
        if b2.items.count() == 0:
            # Add a product and service that will have 0 sales price in snapshot but valid cost
            BudgetItem.objects.create(
                workshop=workshop, budget=b2, product=products[1], quantity=1,
                product_cost_price=products[1].cost_price, product_selling_price=products[1].selling_price
            )
        
        # Ensure WorkOrder for Budget 2
        wo2, _ = WorkOrder.objects.get_or_create(
            budget=b2,
            defaults={"workshop": workshop, "status": WorkOrderStatus.APPROVED, "delivered_at": timezone.now()},
        )

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully!"))
        self.stdout.write(f"Login: admin@hunter.com / admin123")
