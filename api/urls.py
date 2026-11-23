from rest_framework.routers import DefaultRouter

from .views import BookingViewSet, LabViewSet

router = DefaultRouter()
router.register("labs", LabViewSet, basename="lab")
router.register("bookings", BookingViewSet, basename="booking")

urlpatterns = router.urls
