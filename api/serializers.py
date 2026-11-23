from rest_framework import serializers

from .models import Booking, Lab


class LabSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lab
        fields = ("id", "title", "description", "seats")
        read_only_fields = fields


class BookingSerializer(serializers.ModelSerializer):
    quantity = serializers.IntegerField(min_value=1, max_value=1000)
    lab_title = serializers.CharField(source="lab.title", read_only=True)

    class Meta:
        model = Booking
        fields = (
            "id", "owner", "lab", "lab_title", "quantity",
            "status", "created_at", "updated_at",
        )
        read_only_fields = ("id", "owner", "status", "created_at", "updated_at")
