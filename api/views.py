"""ViewSet-и каталогу і заявок."""

from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Booking, Lab
from .serializers import BookingSerializer, LabSerializer
from .services import OrderConflict, OrderRejected, cancel_order, confirm_order


class LabViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Lab.objects.all()
    serializer_class = LabSerializer
    permission_classes = (AllowAny,)


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Booking.objects.filter(owner=self.request.user).select_related("lab")

    def perform_create(self, serializer):
        serializer.save(
            owner=self.request.user,
            status=Booking.Status.DRAFT,
        )

    @action(detail=True, methods=("post",))
    def confirm(self, request, pk=None):
        try:
            booking = confirm_order(int(pk), request.user)
        except Http404:
            return Response({"detail": "Заявку не знайдено."}, status=404)
        except OrderConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except OrderRejected as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking, context={"request": request}).data)

    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None):
        try:
            booking = cancel_order(int(pk), request.user)
        except Http404:
            return Response({"detail": "Заявку не знайдено."}, status=404)
        except OrderConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except OrderRejected as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking, context={"request": request}).data)
