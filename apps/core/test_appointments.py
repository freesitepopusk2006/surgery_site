import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from threading import Barrier
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .appointments import SlotUnavailable, reserve_slot
from .models import AppointmentSlot, BookingRequest, SitePage, SiteSettings
from .notifications import notify_booking


def next_monday():
    today = timezone.localdate()
    return today + timedelta(days=7 - today.weekday())


def future_start():
    return timezone.make_aware(datetime.combine(next_monday(), time(10)))


@override_settings(RESEND_API_KEY='', DEFAULT_FROM_EMAIL='')
class AppointmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = SiteSettings.objects.create(schedule_enabled=True, notification_email='owner@example.com')
        cls.slot = AppointmentSlot.objects.create(starts_at=future_start(), is_demo=True)
        cls.admin = get_user_model().objects.create_superuser(username='schedule-admin', password='test-only-password')

    def setUp(self):
        self.payload = {'slot': self.slot.pk, 'name': 'Тестовый Посетитель', 'phone': '89001234567',
                        'email': 'visitor@example.com', 'consent': 'on', 'website': ''}
        patcher = patch('apps.core.views.notify_booking')
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def reserve(self, **updates):
        return self.client.post(reverse('core:appointment_booking'), {**self.payload, **updates})

    def login_admin(self):
        self.client.force_login(self.admin)

    def decision(self, booking, action):
        return self.client.post(reverse('admin:core_bookingrequest_decision', args=[booking.pk, action]))

    def test_schedule_is_rendered_on_public_pages_and_uses_admin_copy(self):
        self.site.schedule_title = 'Заголовок расписания из админки'
        self.site.save()
        for path in ['/', '/prices/', '/patients/']:
            response = self.client.get(path)
            self.assertContains(response, 'data-scheduler')
            self.assertContains(response, 'Заголовок расписания из админки')
            self.assertContains(response, 'name="email"')
            self.assertNotContains(response, 'owner@example.com')

    def test_week_has_seven_days_and_no_patient_information(self):
        response = self.client.get(reverse('core:appointment_slots'))
        data = response.json()
        self.assertEqual(len(data['days']), 7)
        self.assertEqual(data['week_start'], next_monday().isoformat())
        self.assertEqual(data['days'][0]['slots'][0]['status'], 'free')
        self.assertEqual(data['days'][0]['slots'][0]['time'], '10:00')
        self.assertEqual(data['days'][0]['slots'][0]['end_time'], '10:30')
        self.assertTrue(data['has_demo'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertNotIn('email', response.content.decode())

    def test_reservation_is_durable_before_mail_and_keeps_snapshot(self):
        def notify(booking, **kwargs):
            self.assertTrue(BookingRequest.objects.filter(pk=booking.pk).exists())
            self.assertEqual(kwargs['site_url'], 'http://testserver/')
        self.notify.side_effect = notify
        response = self.reserve()
        self.assertEqual(response.status_code, 201)
        booking = BookingRequest.objects.get()
        self.assertEqual(booking.appointment_start, self.slot.starts_at)
        self.assertEqual(booking.appointment_duration, 30)
        self.assertEqual(booking.appointment_service, self.slot.service)
        self.assertEqual(booking.email, self.payload['email'])
        self.assertEqual(booking.phone, '+79001234567')
        self.assertTrue(booking.is_demo)
        self.assertEqual(booking.status, 'new')
        self.notify.assert_called_once()

    def test_duplicate_retry_does_not_create_second_booking_or_email(self):
        first = self.reserve()
        second = self.reserve()
        self.assertEqual(first.json()['booking_id'], second.json()['booking_id'])
        self.assertEqual(BookingRequest.objects.count(), 1)
        self.notify.assert_called_once()

    def test_other_visitor_cannot_book_held_slot(self):
        self.reserve()
        response = self.reserve(name='Другой Посетитель', email='other@example.com', phone='89001234568')
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()['conflict'])
        slot = self.client.get(reverse('core:appointment_slots')).json()['days'][0]['slots'][0]
        self.assertEqual(slot['status'], 'busy')
        self.assertEqual(BookingRequest.objects.count(), 1)

    def test_confirm_keeps_slot_busy_cancel_releases_and_preserves_history(self):
        self.reserve()
        booking = BookingRequest.objects.get()
        self.login_admin()
        self.assertEqual(self.client.get(reverse('admin:core_bookingrequest_change', args=[booking.pk])).status_code, 200)
        self.assertEqual(self.decision(booking, 'confirm').status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')
        self.assertEqual(self.reserve(phone='89001234568').status_code, 409)
        self.assertEqual(self.decision(booking, 'cancel').status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(self.client.get(reverse('core:appointment_slots')).json()['days'][0]['slots'][0]['status'], 'free')
        self.assertEqual(self.reserve(name='Другой Посетитель', phone='89001234568').status_code, 201)
        self.assertEqual(BookingRequest.objects.count(), 2)
        self.decision(booking, 'confirm')
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')

    def test_database_prevents_two_active_reservations_and_reactivation(self):
        self.reserve()
        booking = BookingRequest.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            BookingRequest.objects.create(slot=self.slot, name='Другой', phone='+79001234568', consent=True)
        booking.status = 'cancelled'
        booking.save()
        BookingRequest.objects.create(slot=self.slot, name='Другой', phone='+79001234568', consent=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BookingRequest.objects.filter(pk=booking.pk).update(status='confirmed')

    def test_hidden_blocked_past_or_missing_slots_cannot_be_reserved(self):
        for index, fields in enumerate([{'is_published': False}, {'is_blocked': True}, {'starts_at': timezone.now() - timedelta(hours=1)}]):
            with self.subTest(fields=fields):
                slot = AppointmentSlot.objects.create(starts_at=self.slot.starts_at + timedelta(hours=index + 2), is_demo=True)
                AppointmentSlot.objects.filter(pk=slot.pk).update(**fields)
                self.assertEqual(self.reserve(slot=slot.pk).status_code, 409)
        self.assertEqual(self.reserve(slot=999999).status_code, 409)
        self.assertFalse(BookingRequest.objects.exists())

    def test_real_slots_require_documents_but_demo_is_explicitly_available(self):
        AppointmentSlot.objects.filter(pk=self.slot.pk).update(is_demo=False)
        self.assertEqual(self.reserve().status_code, 409)
        self.assertEqual(self.client.get(reverse('core:appointment_slots')).json()['days'][0]['slots'][0]['status'], 'closed')
        for slug in ['privacy', 'consent']:
            SitePage.objects.create(title=slug, slug=slug, body='Тест', is_published=True)
        self.assertEqual(self.reserve().status_code, 201)
        self.assertFalse(BookingRequest.objects.get().is_demo)

    def test_invalid_fields_honeypot_and_missing_csrf_are_rejected(self):
        for fields in [{'email': 'wrong'}, {'email': ''}, {'phone': 'bad'}, {'name': ''}, {'consent': ''}, {'website': 'spam'}, {'slot': ''}]:
            with self.subTest(fields=fields):
                self.assertEqual(self.reserve(**fields).status_code, 400)
        response = Client(enforce_csrf_checks=True).post(reverse('core:appointment_booking'), self.payload)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BookingRequest.objects.exists())

    def test_rotated_login_csrf_is_json_and_fresh_token_restores_submission(self):
        client = Client(enforce_csrf_checks=True)
        old = client.get(reverse('core:booking_csrf')).json()['csrfToken']
        client.cookies['csrftoken'] = 'z' * 32
        response = client.post(reverse('core:appointment_booking'), {**self.payload, 'csrfmiddlewaretoken': old})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()['csrf_error'])
        self.assertFalse(BookingRequest.objects.exists())
        refreshed = client.get(reverse('core:booking_csrf'))
        self.assertEqual(refreshed['Cache-Control'], 'no-store')
        fresh = refreshed.json()['csrfToken']
        response = client.post(reverse('core:appointment_booking'), {**self.payload, 'csrfmiddlewaretoken': fresh})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(BookingRequest.objects.count(), 1)

    def test_admin_decisions_require_post_csrf_and_change_permission(self):
        self.reserve()
        booking = BookingRequest.objects.get()
        self.login_admin()
        url = reverse('admin:core_bookingrequest_decision', args=[booking.pk, 'confirm'])
        self.assertEqual(self.client.get(url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        viewer = get_user_model().objects.create_user(username='booking-viewer', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_bookingrequest'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.post(url).status_code, 403)

    def test_booked_slot_cannot_be_silently_moved_and_overlapping_windows_fail(self):
        self.reserve()
        self.slot.starts_at += timedelta(hours=1)
        with self.assertRaises(ValidationError):
            self.slot.full_clean()
        overlapping = AppointmentSlot(starts_at=future_start() + timedelta(minutes=15))
        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_schedule_flags_week_validation_and_rate_limit(self):
        self.assertEqual(self.client.get(reverse('core:appointment_slots'), {'week': 'nonsense'}).status_code, 400)
        self.assertEqual(self.client.get(reverse('core:appointment_slots'), {'week': '2099-01-01'}).status_code, 400)
        self.site.schedule_enabled = False
        self.site.save()
        self.assertEqual(self.reserve().status_code, 503)
        self.assertEqual(self.client.get(reverse('core:appointment_slots')).status_code, 503)
        self.site.schedule_enabled = True
        self.site.save()
        with override_settings(BOOKING_RATE_LIMIT=0):
            self.assertEqual(self.reserve().status_code, 429)

    def test_booking_email_has_requested_contacts_time_and_private_admin_link(self):
        self.reserve()
        booking = BookingRequest.objects.get()
        with patch('apps.core.notifications.send_notification', return_value=('sent', '')) as send:
            notify_booking(booking, site_url='https://example.com/')
        text = send.call_args.args[2]
        for value in [booking.name, booking.email, booking.phone, '10:00', '30 минут', 'ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ',
                      f'https://example.com/admin/core/bookingrequest/{booking.pk}/change/', 'Демонстрационная запись']:
            self.assertIn(value, text)

    def test_generator_uses_admin_forms_and_preserves_existing_windows(self):
        self.login_admin()
        url = reverse('admin:core_appointmentslot_generate')
        self.assertEqual(self.client.get(url).status_code, 200)
        payload = {'start_date': next_monday().isoformat(), 'weekdays': ['0', '1', '2', '3', '4'],
            'start_time': '10:00', 'end_time': '12:00', 'duration': '30', 'service': 'Демо-консультация',
            'is_demo': 'on', 'is_published': 'on', 'break_start': '', 'break_end': ''}
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(AppointmentSlot.objects.count(), 20)
        self.assertEqual(AppointmentSlot.objects.get(pk=self.slot.pk).service, self.slot.service)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(AppointmentSlot.objects.count(), 20)
        response = self.client.post(url, {**payload, 'end_time': '09:00'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)

    def test_generator_respects_breaks_and_access_permissions(self):
        self.login_admin()
        url = reverse('admin:core_appointmentslot_generate')
        payload = {'start_date': next_monday().isoformat(), 'weekdays': ['1'], 'start_time': '10:00',
            'end_time': '14:00', 'duration': '30', 'service': 'Тест', 'is_demo': 'on', 'is_published': 'on',
            'break_start': '11:00', 'break_end': '12:00'}
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        starts = [timezone.localtime(slot.starts_at).strftime('%H:%M') for slot in AppointmentSlot.objects.exclude(pk=self.slot.pk)]
        self.assertNotIn('11:00', starts)
        self.assertNotIn('11:30', starts)
        self.assertEqual(len(starts), 6)
        viewer = get_user_model().objects.create_user(username='schedule-viewer', is_staff=True)
        self.client.force_login(viewer)
        self.assertEqual(self.client.post(url, payload).status_code, 403)


class ConcurrentReservationTests(TransactionTestCase):
    def test_simultaneous_claims_cannot_both_succeed(self):
        site = SiteSettings.objects.create(schedule_enabled=True)
        slot = AppointmentSlot.objects.create(starts_at=future_start(), is_demo=True)
        barrier = Barrier(2)

        def claim(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                data = {'name': f'Посетитель {index}', 'email': f'visitor{index}@example.com', 'phone': f'+7900123456{index}'}
                reserve_slot(slot.pk, data, f'peer-{index}', site)
                return 'reserved'
            except (SlotUnavailable, OperationalError, IntegrityError):
                return 'unavailable'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, [0, 1]))
        self.assertEqual(results.count('reserved'), 1)
        self.assertEqual(BookingRequest.objects.exclude(status='cancelled').count(), 1)
