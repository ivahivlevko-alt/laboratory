from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from api.models import Booking, Lab
from api.services import OrderConflict, OrderRejected, confirm_order


class BookingApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("owner", password="pass")
        self.other = User.objects.create_user("other", password="pass")
        self.lab = Lab.objects.create(title="Лаб 1", seats=2)
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_catalog_is_public(self):
        response = self.client.get("/api/v1/labs/")
        self.assertEqual(response.status_code, 200)

    def test_catalog_search_filters_by_title(self):
        Lab.objects.create(title="Electricity Lab", seats=3)
        response = self.client.get("/api/v1/labs/?search=electric")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([lab["title"] for lab in response.data], ["Electricity Lab"])

    def test_booking_endpoints_require_authentication(self):
        self.assertEqual(self.client.get("/api/v1/bookings/").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/v1/bookings/",
                {"lab": self.lab.pk, "quantity": 1},
                format="json",
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post("/api/v1/bookings/1/confirm/").status_code,
            401,
        )

    def test_create_controls_owner_status_and_quantity(self):
        self.auth(self.owner)
        response = self.client.post("/api/v1/bookings/", {
            "lab": self.lab.pk,
            "quantity": 1,
            "owner": self.other.pk,
            "lab_title": "Forged title",
            "status": "confirmed",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get(pk=response.data["id"])
        self.assertEqual(booking.owner, self.owner)
        self.assertEqual(booking.status, Booking.Status.DRAFT)
        self.assertEqual(response.data["lab_title"], self.lab.title)
        self.assertEqual(Booking.objects.filter(owner=self.owner).count(), 1)

        bad = self.client.post("/api/v1/bookings/", {
            "lab": self.lab.pk,
            "quantity": 0,
        }, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_invalid_booking_data_and_malformed_json_return_400(self):
        self.auth(self.owner)
        for quantity in (-5, 0, 99999999999999999999):
            with self.subTest(quantity=quantity):
                response = self.client.post(
                    "/api/v1/bookings/",
                    {"lab": self.lab.pk, "quantity": quantity},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)

        missing_lab = self.client.post(
            "/api/v1/bookings/",
            {"lab": 999999, "quantity": 1},
            format="json",
        )
        self.assertEqual(missing_lab.status_code, 400)

        malformed = self.client.generic(
            "POST",
            "/api/v1/bookings/",
            data=b'{"quantity":',
            content_type="application/json",
        )
        self.assertEqual(malformed.status_code, 400)

    def test_malformed_action_ids_return_404(self):
        self.auth(self.owner)
        for action in ("confirm", "cancel"):
            with self.subTest(action=action):
                response = self.client.post(
                    f"/api/v1/bookings/not-an-id/{action}/"
                )
                self.assertEqual(response.status_code, 404)

    def test_owner_scoping_and_confirm_cancel(self):
        booking = Booking.objects.create(owner=self.owner, lab=self.lab, quantity=1)
        self.auth(self.other)
        self.assertIn(self.client.get(f"/api/v1/bookings/{booking.pk}/").status_code, (403, 404))

        self.auth(self.owner)
        confirmed = self.client.post(f"/api/v1/bookings/{booking.pk}/confirm/")
        self.assertEqual(confirmed.status_code, 200)
        self.lab.refresh_from_db()
        self.assertEqual(self.lab.seats, 1)

        duplicate = self.client.post(f"/api/v1/bookings/{booking.pk}/confirm/")
        self.assertEqual(duplicate.status_code, 409)

        cancelled = self.client.post(f"/api/v1/bookings/{booking.pk}/cancel/")
        self.assertEqual(cancelled.status_code, 200)
        self.lab.refresh_from_db()
        self.assertEqual(self.lab.seats, 2)

        duplicate_cancel = self.client.post(f"/api/v1/bookings/{booking.pk}/cancel/")
        self.assertEqual(duplicate_cancel.status_code, 409)

    def test_foreign_booking_update_and_delete_are_hidden(self):
        booking = Booking.objects.create(owner=self.owner, lab=self.lab, quantity=1)
        url = f"/api/v1/bookings/{booking.pk}/"

        self.auth(self.other)
        self.assertEqual(self.client.patch(url, {"quantity": 2}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_booking_updates_are_draft_only(self):
        booking = Booking.objects.create(owner=self.owner, lab=self.lab, quantity=1)
        url = f"/api/v1/bookings/{booking.pk}/"
        self.auth(self.owner)
        response = self.client.patch(url, {"quantity": 2}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lab_title"], self.lab.title)
        booking.refresh_from_db()
        self.assertEqual(booking.quantity, 2)

        response = self.client.put(
            url,
            {"lab": self.lab.pk, "quantity": 3, "lab_title": "Forged title"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lab_title"], self.lab.title)
        booking.refresh_from_db()
        self.assertEqual(booking.quantity, 3)

        booking.status = Booking.Status.CONFIRMED
        booking.save()
        response = self.client.patch(url, {"quantity": 4}, format="json")
        self.assertEqual(response.status_code, 409)
        booking.refresh_from_db()
        self.assertEqual(booking.quantity, 3)

    def test_confirmed_booking_cannot_be_deleted(self):
        booking = Booking.objects.create(
            owner=self.owner,
            lab=self.lab,
            quantity=1,
            status=Booking.Status.CONFIRMED,
        )
        self.auth(self.owner)
        response = self.client.delete(f"/api/v1/bookings/{booking.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Booking.objects.filter(pk=booking.pk).exists())

    def test_draft_and_cancelled_bookings_can_be_deleted(self):
        self.auth(self.owner)
        for booking_status in (Booking.Status.DRAFT, Booking.Status.CANCELLED):
            booking = Booking.objects.create(
                owner=self.owner,
                lab=self.lab,
                quantity=1,
                status=booking_status,
            )
            response = self.client.delete(f"/api/v1/bookings/{booking.pk}/")
            self.assertEqual(response.status_code, 204)
            self.assertFalse(Booking.objects.filter(pk=booking.pk).exists())

    def test_confirm_rejects_insufficient_seats(self):
        self.lab.seats = 1
        self.lab.save()
        booking = Booking.objects.create(owner=self.owner, lab=self.lab, quantity=2)
        self.auth(self.owner)
        response = self.client.post(f"/api/v1/bookings/{booking.pk}/confirm/")
        self.assertEqual(response.status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.DRAFT)

    def test_seeded_attack_users_are_not_admins_and_default_admin_passwords_fail(self):
        call_command("seed_attack", verbosity=0)
        User = get_user_model()
        for username in ("attacker1", "attacker2"):
            user = User.objects.get(username=username)
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)

        self.assertFalse(self.client.login(username="admin", password="admin"))
        self.assertFalse(self.client.login(username="admin", password="1234"))


class BookingConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("race-owner")
        self.lab = Lab.objects.create(title="Concurrent lab", seats=3)

    def race_confirms(self, booking_ids):
        barrier = Barrier(len(booking_ids))

        def confirm(booking_id):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                confirm_order(booking_id, self.owner)
                return "confirmed"
            except OrderConflict:
                return "conflict"
            except OrderRejected:
                return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(booking_ids)) as executor:
            return list(executor.map(confirm, booking_ids))

    def test_concurrent_confirms_of_one_booking_only_reserve_once(self):
        self.lab.seats = 10
        self.lab.save()
        booking = Booking.objects.create(owner=self.owner, lab=self.lab, quantity=1)

        results = self.race_confirms([booking.pk] * 8)

        self.assertEqual(results.count("confirmed"), 1)
        self.assertEqual(results.count("conflict"), 7)
        self.lab.refresh_from_db()
        self.assertEqual(self.lab.seats, 9)

    def test_concurrent_bookings_cannot_oversell_inventory(self):
        bookings = [
            Booking.objects.create(owner=self.owner, lab=self.lab, quantity=1)
            for _ in range(8)
        ]

        results = self.race_confirms([booking.pk for booking in bookings])

        self.assertEqual(results.count("confirmed"), 3)
        self.assertEqual(results.count("rejected"), 5)
        self.lab.refresh_from_db()
        self.assertEqual(self.lab.seats, 0)
        self.assertEqual(
            Booking.objects.filter(status=Booking.Status.CONFIRMED).count(),
            3,
        )
