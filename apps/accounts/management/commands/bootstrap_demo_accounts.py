from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import StaffProfile


class Command(BaseCommand):
    help = "Create or refresh predictable demo accounts for landlord, manager, and staff."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="strong-pass-123",
            help="Password applied to all demo accounts (default: strong-pass-123).",
        )

    def _upsert_user(
        self,
        *,
        username,
        password,
        role,
        first_name,
        last_name,
        email,
        job_title,
        phone,
        superuser=False,
    ):
        user_model = get_user_model()
        user, _created = user_model.objects.get_or_create(username=username)
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.is_active = True
        user.is_staff = superuser
        user.is_superuser = superuser
        user.set_password(password)
        user.save()

        profile = user.staff_profile
        profile.role = role
        profile.job_title = job_title
        profile.phone = phone
        profile.is_active = True
        profile.notify_on_shift_assignment = True
        profile.save()

        return user

    def handle(self, *args, **options):
        password = options["password"]

        users = [
            {
                "username": "landlord",
                "role": StaffProfile.Role.LANDLORD,
                "first_name": "Alex",
                "last_name": "Landlord",
                "email": "landlord@barrelboss.local",
                "job_title": "Landlord",
                "phone": "07000000001",
                "superuser": True,
            },
            {
                "username": "manager",
                "role": StaffProfile.Role.MANAGER,
                "first_name": "Morgan",
                "last_name": "Manager",
                "email": "manager@barrelboss.local",
                "job_title": "Bar Manager",
                "phone": "07000000002",
                "superuser": False,
            },
            {
                "username": "staff",
                "role": StaffProfile.Role.STAFF,
                "first_name": "Taylor",
                "last_name": "Staff",
                "email": "staff@barrelboss.local",
                "job_title": "Bartender",
                "phone": "07000000003",
                "superuser": False,
            },
        ]

        for row in users:
            self._upsert_user(password=password, **row)

        self.stdout.write(self.style.SUCCESS("Demo accounts ready:"))
        for row in users:
            self.stdout.write(
                f" - {row['username']} / {password} ({StaffProfile.Role(row['role']).label})"
            )
