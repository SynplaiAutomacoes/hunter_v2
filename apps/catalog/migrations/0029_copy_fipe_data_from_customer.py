from django.db import migrations


def copy_fipe_data_from_customer(apps, schema_editor):
    CustomerBrand = apps.get_model("customer", "FipeVehicleBrand")
    CustomerModel = apps.get_model("customer", "FipeVehicleModel")
    CustomerFuelCache = apps.get_model("customer", "FipeModelFuelCache")
    CustomerSyncState = apps.get_model("customer", "FipeSyncState")

    CatalogBrand = apps.get_model("catalog", "FipeVehicleBrand")
    CatalogModel = apps.get_model("catalog", "FipeVehicleModel")
    CatalogFuelCache = apps.get_model("catalog", "FipeModelFuelCache")
    CatalogSyncState = apps.get_model("catalog", "FipeSyncState")

    brand_id_map: dict[int, int] = {}
    model_id_map: dict[int, int] = {}

    for brand in CustomerBrand.objects.all().iterator():
        copied_brand = CatalogBrand.objects.create(
            vehicle_type=brand.vehicle_type,
            external_id=brand.external_id,
            name=brand.name,
            is_active=brand.is_active,
            criado_em=brand.criado_em,
            atualizado_em=brand.atualizado_em,
        )
        brand_id_map[brand.pk] = copied_brand.pk

    for model in CustomerModel.objects.all().iterator():
        copied_model = CatalogModel.objects.create(
            brand_id=brand_id_map[model.brand_id],
            vehicle_type=model.vehicle_type,
            external_id=model.external_id,
            name=model.name,
            is_active=model.is_active,
            criado_em=model.criado_em,
            atualizado_em=model.atualizado_em,
        )
        model_id_map[model.pk] = copied_model.pk

    for fuel_cache in CustomerFuelCache.objects.all().iterator():
        CatalogFuelCache.objects.create(
            model_id=model_id_map[fuel_cache.model_id],
            vehicle_type=fuel_cache.vehicle_type,
            fuel_values=fuel_cache.fuel_values,
            source_year_count=fuel_cache.source_year_count,
            last_synced_at=fuel_cache.last_synced_at,
            criado_em=fuel_cache.criado_em,
            atualizado_em=fuel_cache.atualizado_em,
        )

    for sync_state in CustomerSyncState.objects.all().iterator():
        CatalogSyncState.objects.create(
            scope=sync_state.scope,
            access_count=sync_state.access_count,
            last_full_sync_at=sync_state.last_full_sync_at,
            last_sync_started_at=sync_state.last_sync_started_at,
            sync_in_progress=sync_state.sync_in_progress,
            last_sync_error=sync_state.last_sync_error,
            criado_em=sync_state.criado_em,
            atualizado_em=sync_state.atualizado_em,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0028_fipesyncstate_fipevehiclebrand_fipevehiclemodel_and_more"),
        ("customer", "0015_fipesyncstate_alter_vehicle_engine_fipevehiclebrand_and_more"),
    ]

    operations = [migrations.RunPython(copy_fipe_data_from_customer, migrations.RunPython.noop)]
