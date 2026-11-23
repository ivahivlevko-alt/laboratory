"""Серіалізатори каталогу та заявок."""

from rest_framework import serializers

from .models import Booking, Lab


class LabSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lab
        fields = ("id", "title", "description", "seats")
        read_only_fields = fields


class BookingSerializer(serializers.ModelSerializer):
    quantity = serializers.IntegerField(min_value=1, max_value=2147483647)

    class Meta:
        model = Booking
        fields = (
            "id", "owner", "lab", "quantity", "status",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "owner", "status", "created_at", "updated_at",
        )

    def create(self, validated_data):
        validated_data["owner"] = self.context["request"].user
        validated_data["status"] = Booking.Status.DRAFT
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if instance.status != Booking.Status.DRAFT:
            raise serializers.ValidationError("Редагувати можна лише заявку у стані draft.")
        return super().update(instance, validated_data)
