"""Роль «Моделі». Перші 30 хвилин дня цей файл пише вся команда разом.

Що має бути:
- елемент каталогу з числовим полем залишку (`PositiveIntegerField`);
- заявка: власник (FK на User), елемент (FK), кількість, `status`
  зі значеннями рівно `draft` / `confirmed` / `cancelled`;
- `CheckConstraint`, що залишок не від'ємний, — страхувальна сітка, а не головний захист.
"""
from django.db import models  # noqa: F401

from django.conf import settings
from django.db.models import Q


class Lab(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    seats = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=Q(seats__gte=0),
                name="lab_seats_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.seats} місць)"


class Booking(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        CONFIRMED = "confirmed", "confirmed"
        CANCELLED = "cancelled", "cancelled"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    lab = models.ForeignKey(
        Lab,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-id",)
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="booking_quantity_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "status"], name="booking_owner_status_idx"),
            models.Index(fields=["lab", "status"], name="booking_lab_status_idx"),
        ]

    def __str__(self):
        return f"Booking #{self.pk}: {self.owner} → {self.lab_id} x{self.quantity} [{self.status}]"