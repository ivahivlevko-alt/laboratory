from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Booking, Lab

ATTACKERS = {
    "attacker1": "attack-pass-1",
    "attacker2": "attack-pass-2",
}

LABS = {
    1: (1, "Лабораторна робота №1 · Оптика (пробне місце)"),
    2: (50, "Лабораторна робота №2 · Механіка"),
    3: (50, "Лабораторна робота №3 · Електрика"),
    4: (50, "Лабораторна робота №4 · Хімія"),
}

RACE_ITEM = 1


class Command(BaseCommand):
    help = "Idempotent seed for the attack script: attackers, labs 1-4, no bookings."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()

        for username, password in ATTACKERS.items():
            user, _ = User.objects.get_or_create(username=username)
            user.is_staff = False
            user.is_superuser = False
            user.is_active = True
            user.set_password(password)
            user.save()

        # Спочатку заявки: FK на Lab має PROTECT, інакше видалення лабораторних впаде.
        Booking.objects.all().delete()

        for pk, (seats, title) in LABS.items():
            Lab.objects.update_or_create(
                pk=pk,
                defaults={"title": title, "seats": seats, "description": ""},
            )
        Lab.objects.exclude(pk__in=LABS.keys()).delete()

        race = Lab.objects.get(pk=RACE_ITEM)
        self.stdout.write(
            self.style.SUCCESS(f"race_item={RACE_ITEM}, seats={race.seats}")
        )