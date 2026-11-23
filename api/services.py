"""Роль «Стійкість». Уся бухгалтерія ресурсу — тут, а не у views.

Головне правило дня: ресурс зайнятий тоді й лише тоді, коли заявка в стані
`confirmed`. Кожна функція — одна `transaction.atomic()` і умовні UPDATE.

Чому саме так:
- `filter(status="draft").update(...)` повертає кількість змінених рядків.
  База вирішує це атомарно: два одночасні confirm не можуть обидва отримати 1.
- `filter(seats__gte=qty).update(seats=F("seats") - qty)` так само не дає
  продати останнє місце двічі.
- Обидва UPDATE — в одній транзакції: якщо другий не спрацював, кидаємо
  виняток, і перший відкочується.
"""
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import Http404

from .models import Booking, Lab


class OrderError(Exception):
    """Базова помилка бізнес-операції із заявкою."""


class OrderConflict(OrderError):
    """Перехід, якого немає на схемі станів, або заявка вже не та → 409."""


class OrderRejected(OrderError):
    """Некоректна операція з даними (наприклад, бракує місць) → 400."""


def _get_owned_order(order_id: int, user) -> Booking:
    """Заявка видима лише власнику; чужу віддаємо як 404, не розкриваючи існування."""
    try:
        return (
            Booking.objects.select_for_update()
            .select_related("lab")
            .get(pk=order_id, owner=user)
        )
    except Booking.DoesNotExist as exc:
        raise Http404("Заявку не знайдено.") from exc


def confirm_order(order_id: int, user) -> Booking:
    """draft → confirmed із зайняттям місць. Повторний confirm → OrderConflict."""
    try:
        with transaction.atomic():
            order = _get_owned_order(order_id, user)

            # 1. Атомарно забираємо саме чернетку. 0 рядків = хтось уже
            #    підтвердив/скасував (або це не draft) → 409.
            claimed = Booking.objects.filter(
                pk=order.pk,
                owner=user,
                status=Booking.Status.DRAFT,
            ).update(status=Booking.Status.CONFIRMED)
            if claimed != 1:
                raise OrderConflict("Підтвердити можна лише чернетку (draft).")

            # 2. Атомарно резервуємо місця. Якщо місць не вистачає, UPDATE
            #    змінить 0 рядків, виняток відкотить і крок 1.
            reserved = Lab.objects.filter(
                pk=order.lab_id,
                seats__gte=order.quantity,
            ).update(seats=F("seats") - order.quantity)
            if reserved != 1:
                raise OrderRejected("На лабораторній роботі недостатньо вільних місць.")

            order.refresh_from_db()
            return order
    except IntegrityError as exc:
        # CheckConstraint — остання сітка. Назовні не має витікати 500.
        raise OrderRejected("Операція порушила цілісність залишку.") from exc


def cancel_order(order_id: int, user) -> Booking:
    """Скасовує draft без зміни залишку або confirmed із поверненням місць."""
    try:
        with transaction.atomic():
            order = _get_owned_order(order_id, user)

            if order.status not in (
                Booking.Status.DRAFT,
                Booking.Status.CONFIRMED,
            ):
                raise OrderConflict(
                    "Скасувати можна лише заявку у стані draft або confirmed."
                )

            # Статус є умовою переходу, тож лише один конкурентний cancel
            # може перевести заявку в cancelled і повернути зайняті місця.
            cancelled = Booking.objects.filter(
                pk=order.pk,
                owner=user,
                status=order.status,
            ).update(status=Booking.Status.CANCELLED)
            if cancelled != 1:
                raise OrderConflict("Заявка вже змінила стан.")

            if order.status == Booking.Status.CONFIRMED:
                returned = Lab.objects.filter(pk=order.lab_id).update(
                    seats=F("seats") + order.quantity
                )
                if returned != 1:
                    raise OrderRejected("Не вдалося повернути місця до каталогу.")

            order.refresh_from_db()
            return order
    except IntegrityError as exc:
        raise OrderRejected("Операція порушила цілісність залишку.") from exc
