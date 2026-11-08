from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AppointmentSlot, BookingRequest, PatientCategory, PatientPage, HomePage, SiteSettings, SitePage


class OwnerAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_superuser('owner', password='test-password')
        today = timezone.localdate()
        cls.week = today + timedelta(days=7 - today.weekday())
        cls.slot = AppointmentSlot.objects.create(
            starts_at=timezone.make_aware(datetime.combine(cls.week, time(10))), is_demo=True)

    def setUp(self):
        self.client.force_login(self.owner)
        self.calendar = reverse('admin:core_appointmentslot_calendar')
        self.edit = reverse('admin:core_appointmentslot_edit_window', args=[self.slot.pk])

    def booking(self):
        return BookingRequest.objects.create(name='Пациент с бронью', phone='+79001234567',
            email='visitor@example.com', consent=True, slot=self.slot,
            appointment_start=self.slot.starts_at, appointment_duration=30,
            appointment_service=self.slot.service, is_demo=True)

    def payload(self, **updates):
        return {'starts_at': timezone.localtime(self.slot.starts_at).strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 30, 'service': self.slot.service,
                'is_demo': 'on', 'availability': 'open', 'note': '', **updates}

    def test_owner_dashboard_calendar_and_all_editor_screens_render(self):
        site = SiteSettings.objects.create()
        home = HomePage.objects.create()
        category = PatientCategory.objects.create(title='Категория', slug='category')
        page = PatientPage.objects.create(title='Статья', slug='article', category=category)
        for url in [reverse('admin:index'), self.calendar, self.edit,
                    self.edit + '?panel=1', reverse('admin:core_appointmentslot_new_window'),
                    reverse('admin:core_appointmentslot_change', args=[self.slot.pk]),
                    reverse('admin:core_appointmentslot_add'),
                    reverse('admin:core_appointmentslot_generate'),
                    reverse('admin:core_appointmentslot_copy') + '?week=' + self.week.isoformat(),
                    reverse('admin:core_appointmentslot_table'),
                    reverse('admin:core_sitesettings_change', args=[site.pk]),
                    reverse('admin:core_homepage_change', args=[home.pk]),
                    reverse('admin:core_patientpage_change', args=[page.pk])]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(self.calendar), '10:00–10:30')
        self.assertRedirects(self.client.get(reverse('admin:core_appointmentslot_changelist')), self.calendar)

    def test_day_close_open_preserves_bookings_hidden_flags_and_logs(self):
        booking = self.booking()
        self.slot.is_published = False
        self.slot.save()
        url = reverse('admin:core_appointmentslot_day')
        self.assertEqual(self.client.get(url).status_code, 405)
        for operation in ('close', 'open'):
            self.client.post(url, {'day': self.week.isoformat(), 'operation': operation})
            self.slot.refresh_from_db()
            booking.refresh_from_db()
            self.assertEqual(self.slot.is_blocked, operation == 'close')
            self.assertFalse(self.slot.is_published)
            self.assertEqual(booking.status, 'new')
        self.assertEqual(self.slot.reservation_version, 2)

    def test_occupied_window_ignores_tampered_date_and_keeps_snapshot(self):
        booking = self.booking()
        response = self.client.post(self.edit, self.payload(starts_at='2099-01-01T12:00',
            service='Подмена', duration_minutes=60, availability='closed', note='Перезвонить'))
        self.assertEqual(response.status_code, 302)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.starts_at, booking.appointment_start)
        self.assertEqual(self.slot.service, booking.appointment_service)
        self.assertEqual(self.slot.duration_minutes, 30)
        self.assertTrue(self.slot.is_demo)
        self.assertTrue(self.slot.is_blocked)
        self.assertEqual(self.slot.note, 'Перезвонить')

    def test_overlap_rejected_without_changing_existing_window(self):
        other = AppointmentSlot.objects.create(starts_at=self.slot.starts_at + timedelta(hours=1), is_demo=True)
        response = self.client.post(self.edit, self.payload(
            starts_at=timezone.localtime(other.starts_at - timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M')))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'пересекается')
        self.slot.refresh_from_db()
        self.assertEqual(timezone.localtime(self.slot.starts_at).hour, 10)

    def test_copy_week_preserves_existing_and_does_not_copy_personal_data(self):
        self.booking()
        self.slot.note = 'Личная заметка о пациенте'
        self.slot.save()
        target = self.week + timedelta(days=7)
        existing = AppointmentSlot.objects.create(starts_at=self.slot.starts_at + timedelta(days=7, hours=1),
                                                   service='Существующая услуга', is_blocked=True)
        url = reverse('admin:core_appointmentslot_copy')
        data = {'week': self.week.isoformat(), 'target': target.isoformat()}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        copied = AppointmentSlot.objects.get(starts_at=self.slot.starts_at + timedelta(days=7))
        self.assertTrue(copied.is_demo)
        self.assertEqual(copied.note, '')
        self.assertFalse(copied.bookings.exists())
        self.assertEqual(BookingRequest.objects.count(), 1)
        self.client.post(url, data)
        self.assertEqual(AppointmentSlot.objects.count(), 3)
        existing.refresh_from_db()
        self.assertEqual(existing.service, 'Существующая услуга')
        self.assertTrue(existing.is_blocked)

    def test_copy_overlap_rolls_back_entire_week(self):
        AppointmentSlot.objects.create(starts_at=self.slot.starts_at + timedelta(hours=1), is_demo=True)
        AppointmentSlot.objects.create(starts_at=self.slot.starts_at + timedelta(days=7, hours=1, minutes=15))
        response = self.client.post(reverse('admin:core_appointmentslot_copy'),
            {'week': self.week.isoformat(), 'target': (self.week + timedelta(days=7)).isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ничего не скопировано')
        self.assertEqual(AppointmentSlot.objects.count(), 3)

    def test_permissions_hide_patient_data_and_prevent_writes(self):
        self.booking()
        staff = get_user_model().objects.create_user('viewer', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_appointmentslot'))
        self.client.force_login(staff)
        self.assertContains(self.client.get(self.calendar), 'Занято')
        for url in [self.calendar, self.edit, reverse('admin:index')]:
            response = self.client.get(url)
            self.assertNotContains(response, 'Пациент с бронью')
            self.assertNotContains(response, 'visitor@example.com')
        self.assertEqual(self.client.post(self.edit, self.payload()).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:core_appointmentslot_day'),
            {'day': self.week.isoformat(), 'operation': 'close'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:core_appointmentslot_copy'),
            {'week': self.week.isoformat()}).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:core_appointmentslot_generate')).status_code, 403)

    def test_new_endpoints_require_csrf(self):
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.owner)
        for url, data in [(self.edit, self.payload()),
                          (reverse('admin:core_appointmentslot_day'), {'day': self.week.isoformat(), 'operation': 'close'}),
                          (reverse('admin:core_appointmentslot_copy'), {'week': self.week.isoformat(), 'target': self.week.isoformat()})]:
            self.assertEqual(protected.post(url, data).status_code, 403)

    def test_booking_decision_returns_to_calendar_and_rejects_external_redirect(self):
        booking = self.booking()
        url = reverse('admin:core_bookingrequest_decision', args=[booking.pk, 'confirm'])
        back = self.calendar + '?week=' + self.week.isoformat()
        self.assertEqual(self.client.post(url, {'next': back})['Location'], back)
        self.assertEqual(self.client.post(url, {'next': 'https://example.com/steal'})['Location'],
                         reverse('admin:core_bookingrequest_change', args=[booking.pk]))

    def test_article_address_is_automatic_and_existing_url_is_preserved(self):
        category = PatientCategory.objects.create(title='Категория', slug='category')
        data = {'category': category.pk, 'title': 'Новая статья', 'description': '', 'slug': '', 'order': 0}
        # The concrete form fields are supplied by ModelAdmin in real use.
        from django.contrib import admin
        request = type('Request', (), {'user': self.owner})()
        form_class = admin.site._registry[PatientPage].get_form(request)
        form = form_class(data)
        self.assertTrue(form.is_valid(), form.errors)
        page = form.save()
        original = page.slug
        form = form_class({**data, 'title': 'Изменённое название'}, instance=page)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().slug, original)

    def test_document_type_creates_required_address_and_prevents_duplicates(self):
        from django.contrib import admin
        request = type('Request', (), {'user': self.owner})()
        form_class = admin.site._registry[SitePage].get_form(request)
        data = {'purpose': 'consent', 'title': 'Согласие', 'body': 'Текст документа', 'is_published': 'on', 'slug': ''}
        form = form_class(data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().slug, 'consent')
        self.assertFalse(form_class(data).is_valid())

    def test_single_window_can_be_added_and_hidden_without_hardcoded_content(self):
        url = reverse('admin:core_appointmentslot_new_window')
        when = timezone.localtime(self.slot.starts_at + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
        response = self.client.post(url, self.payload(starts_at=when, service='Услуга из формы',
            availability='hidden', duration_minutes=45))
        self.assertEqual(response.status_code, 302)
        slot = AppointmentSlot.objects.get(service='Услуга из формы')
        self.assertFalse(slot.is_published)
        self.assertEqual(slot.duration_minutes, 45)
        self.assertTrue(slot.is_demo)
