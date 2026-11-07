from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Exists, F, OuterRef
from django.utils import timezone

from .models import AppointmentSlot, BookingRequest, SitePage


class SlotUnavailable(Exception):
    pass


def documents_ready(site):
    return (bool(site.privacy_policy_url) or SitePage.objects.filter(slug='privacy', is_published=True).exists()) and (
        SitePage.objects.filter(slug='consent', is_published=True).exists())


def schedule_data(site, week=None):
    today = timezone.localdate()
    first_week = today - timedelta(days=today.weekday())
    last_week = first_week + timedelta(weeks=12)
    if week:
        start = date.fromisoformat(week)
        if start.weekday() or not first_week <= start <= last_week:
            raise ValueError('Week out of range')
    else:
        earliest = AppointmentSlot.objects.filter(is_published=True, starts_at__gt=timezone.now(),
            starts_at__lt=timezone.make_aware(datetime.combine(last_week + timedelta(days=7), time.min))).first()
        day = timezone.localdate(earliest.starts_at) if earliest else today
        start = day - timedelta(days=day.weekday())
    end = start + timedelta(days=7)
    active = BookingRequest.objects.filter(slot_id=OuterRef('pk')).exclude(status=BookingRequest.Status.CANCELLED)
    slots = AppointmentSlot.objects.filter(is_published=True,
        starts_at__gte=timezone.make_aware(datetime.combine(start, time.min)),
        starts_at__lt=timezone.make_aware(datetime.combine(end, time.min))).annotate(taken=Exists(active))
    ready = documents_ready(site)
    labels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    days = [{'date': (start + timedelta(days=i)).isoformat(), 'label': labels[i],
        'number': (start + timedelta(days=i)).day, 'slots': []} for i in range(7)]
    for slot in slots:
        begins = timezone.localtime(slot.starts_at)
        available = not slot.taken and not slot.is_blocked and slot.starts_at > timezone.now()
        status = 'free' if available and (slot.is_demo or ready) else 'busy' if slot.taken else 'closed'
        days[begins.weekday()]['slots'].append({'id': slot.pk, 'time': begins.strftime('%H:%M'),
            'end_time': timezone.localtime(slot.ends_at).strftime('%H:%M'), 'service': slot.service,
            'duration': slot.duration_minutes, 'demo': slot.is_demo, 'status': status,
            'label': f'{begins:%d.%m.%Y} · {begins:%H:%M}–{timezone.localtime(slot.ends_at):%H:%M}'})
    return {'week_start': start.isoformat(), 'week_label': f'{start:%d.%m} — {(end - timedelta(days=1)):%d.%m.%Y}',
        'previous': (start - timedelta(days=7)).isoformat() if start > first_week else None,
        'next': end.isoformat() if start < last_week else None, 'days': days,
        'has_demo': any(slot['demo'] for day in days for slot in day['slots']), 'timezone': 'Москва, UTC+3'}


def reserve_slot(slot_id, data, throttle, site):
    with transaction.atomic():
        # The first operation is a write: this serializes claim attempts on SQLite
        # as well as PostgreSQL, without relying on SQLite's no-op select_for_update.
        claimed = AppointmentSlot.objects.filter(pk=slot_id, is_published=True, is_blocked=False,
            starts_at__gt=timezone.now()).update(reservation_version=F('reservation_version') + 1)
        if not claimed:
            raise SlotUnavailable
        slot = AppointmentSlot.objects.get(pk=slot_id)
        if slot.bookings.exclude(status=BookingRequest.Status.CANCELLED).exists():
            raise SlotUnavailable
        if not slot.is_demo and not documents_ready(site):
            raise SlotUnavailable
        return BookingRequest.objects.create(slot=slot, name=data['name'], email=data['email'], phone=data['phone'],
            consent=True, consent_document='demo-booking' if slot.is_demo else '/pages/consent/',
            throttle_key=throttle, appointment_start=slot.starts_at, appointment_duration=slot.duration_minutes,
            appointment_service=slot.service, is_demo=slot.is_demo)
