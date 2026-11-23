from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from . import services
from .models import Booking, Lab
from .permissions import IsOwner
from .serializers import BookingSerializer, LabSerializer


class StateConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Конфлікт зі станом ресурсу."
    default_code = "state_conflict"


class LabViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Lab.objects.all()
    serializer_class = LabSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search)
        return qs


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Booking.objects.none()
        return Booking.objects.filter(owner=user).select_related("lab")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, status=Booking.Status.DRAFT)

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            instance = self.get_object()
            if instance.status != Booking.Status.DRAFT:
                raise StateConflict("Змінювати можна лише чернетку (draft).")
            return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            instance = self.get_object()
            if instance.status == Booking.Status.CONFIRMED:
                raise StateConflict(
                    "Підтверджену заявку не можна видалити — спершу скасуйте її."
                )
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def confirm(self, request, *args, **kwargs):
        order = self.get_object()
        try:
            order = services.confirm_order(order.pk, request.user)
        except services.OrderConflict as exc:
            raise StateConflict(str(exc)) from exc
        except services.OrderRejected as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        order = self.get_object()
        try:
            order = services.cancel_order(order.pk, request.user)
        except services.OrderConflict as exc:
            raise StateConflict(str(exc)) from exc
        except services.OrderRejected as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(order).data)

