from django.contrib import admin  # noqa: F401

# Роль «Моделі»: зареєструйте обидві моделі, щоб бачити залишок під час атаки.

from .models import Booking, Lab


@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "seats")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "lab", "quantity", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("owner__username", "lab__title")