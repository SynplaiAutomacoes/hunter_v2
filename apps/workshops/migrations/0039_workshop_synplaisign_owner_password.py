from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workshops", "0038_alter_workshopcost_total_monthly_costs_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshop",
            name="synplaisign_owner_password",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Senha aleatoria do OWNER na SynplaiSign (criptografada). Nao e a senha do Hunter.",
                max_length=512,
                verbose_name="SynplaiSign Owner Password",
            ),
        ),
    ]
