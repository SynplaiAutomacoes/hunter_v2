from django.core.management.base import BaseCommand
from django.db import transaction
from apps.workorder.models import WorkOrder

class Command(BaseCommand):
    help = "Fixes WorkOrders whose budget_type does not match their linked Budget's budget_type"

    def handle(self, *args, **options):
        from django.db.models import F

        inconsistent_wos = WorkOrder.objects.annotate(
            actual_budget_type=F("budget__budget_type")
        ).exclude(
            budget_type=F("budget__budget_type")
        )

        count = inconsistent_wos.count()
        self.stdout.write(self.style.WARNING(f"Found {count} inconsistent WorkOrders."))

        if count == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to fix!"))
            return

        with transaction.atomic():
            for wo in inconsistent_wos:
                old_type = wo.budget_type
                new_type = wo.budget.budget_type
                self.stdout.write(f"Fixing WorkOrder ID: {wo.id} (linked to Budget ID: {wo.budget_id})...")
                self.stdout.write(f"  Changing budget_type from '{old_type}' to '{new_type}'")
                
                wo.budget_type = new_type
                wo.save(update_fields=["budget_type"])
                
                updated_items_count = wo.sync_items_benefit_type_to_budget_type()
                self.stdout.write(f"  Synced {updated_items_count} items' benefit types.")
                
                wo.invalidate_pricing_snapshot_cache()
                wo.refresh_stored_amounts()
                
                self.stdout.write(self.style.SUCCESS(f"  WorkOrder ID: {wo.id} updated successfully! New stored_total_amount: {wo.stored_total_amount}"))

        self.stdout.write(self.style.SUCCESS(f"Successfully corrected {count} WorkOrders."))
