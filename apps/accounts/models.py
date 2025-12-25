from django.contrib.auth.models import AbstractUser
from django.db.models import CharField, ManyToManyField, TextChoices
from localflavor.br.models import BRCPFField
from apps.workshops.models import Workshop


class User(AbstractUser):
    class Role(TextChoices):
        ADMIN = "ADM", "Administrator"
        MANAGER = "MGR", "Manager"
        MECHANIC = "MEC", "Mechanic"

    cpf = BRCPFField(unique=True, null=False, blank=False)
    role = CharField(max_length=3, choices=Role.choices, default=Role.ADMIN)
    workshops = ManyToManyField(Workshop, related_name="users", blank=True)

    def __str__(self):
        return f"{self.first_name} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_manager(self):
        """Checks if user has management privileges"""
        return self.role in [self.Role.ADMIN, self.Role.MANAGER]
