"""Owner-facing schedule. All writes keep the public reservation lock protocol."""
from datetime import date, datetime, time, timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.http import Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from .models import AppointmentSlot, BookingRequest


def monday(value):
    return value - timedelta(days=value.weekday())


def parse_day(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise Http404('Дата не найдена')


def bounds(day):
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=7)


class WindowForm(forms.ModelForm):
    starts_at = forms.DateTimeField(label='Дата и время', input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}))
    availability = forms.ChoiceField(label='Доступность', choices=[
        ('open', 'Открыто для записи'), ('closed', 'Закрыто для записи'), ('hidden', 'Скрыто с сайта')])

    class Meta:
        model = AppointmentSlot
        fields = ('starts_at', 'duration_minutes', 'service', 'is_demo', 'note')
        widgets = {'note': forms.Textarea(attrs={'rows': 3})}
        labels = {'duration_minutes': 'Длительность в минутах', 'note': 'Заметка для себя'}
        help_texts = {'note': 'Посетители эту заметку не видят.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        slot = self.instance
        if slot.pk:
            self.fields['availability'].initial = ('hidden' if not slot.is_published
                                                   else 'closed' if slot.is_blocked else 'open')
            if slot.bookings.exclude(status='cancelled').exists():
                for name in ('starts_at', 'duration_minutes', 'service', 'is_demo'):
                    self.fields[name].disabled = True

    def clean(self):
        data = super().clean()
        state = data.get('availability')
        self.instance.is_published = state != 'hidden'
        self.instance.is_blocked = state == 'closed'
        if not self.instance.pk and data.get('starts_at') and data['starts_at'] <= timezone.now():
            self.add_error('starts_at', 'Новое окно должно быть в будущем.')
        return data


class CopyWeekForm(forms.Form):
    target = forms.DateField(label='Неделя, в которую скопировать',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        help_text='Выберите любой день нужной недели. Копируются дни и часы, без записей пациентов.')

    def clean_target(self):
        value = monday(self.cleaned_data['target'])
        if value < timezone.localdate():
            raise forms.ValidationError('Выберите следующую или более позднюю неделю.')
        return value


class OwnerScheduleMixin:
    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path('calendar/', wrap(self.calendar_view), name='core_appointmentslot_calendar'),
            path('calendar/new/', wrap(self.window_view), name='core_appointmentslot_new_window'),
            path('<int:object_id>/edit-window/', wrap(self.window_view), name='core_appointmentslot_edit_window'),
            path('calendar/day/', wrap(self.day_view), name='core_appointmentslot_day'),
            path('calendar/copy/', wrap(self.copy_view), name='core_appointmentslot_copy'),
            path('table/', wrap(super().changelist_view), name='core_appointmentslot_table'),
        ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse('admin:core_appointmentslot_calendar'))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        # Old bookmarks and the advanced table use the same reservation-safe editor.
        return self.window_view(request, object_id=object_id)

    def add_view(self, request, form_url='', extra_context=None):
        return self.window_view(request)

    def calendar_url(self, week):
        return reverse('admin:core_appointmentslot_calendar') + '?week=' + week.isoformat()

    def calendar_view(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        today = timezone.localdate()
        if request.GET.get('week'):
            week = monday(parse_day(request.GET['week']))
        else:
            first = AppointmentSlot.objects.filter(starts_at__gte=timezone.now()).first()
            week = monday(timezone.localdate(first.starts_at) if first else today)
        start, end = bounds(week)
        slots = list(self.get_queryset(request).filter(starts_at__gte=start, starts_at__lt=end))
        booking_admin = self.admin_site._registry.get(BookingRequest)
        can_bookings = booking_admin and booking_admin.has_view_or_change_permission(request)
        bookings = {item.slot_id: item for item in BookingRequest.objects.filter(
            slot_id__in=[slot.pk for slot in slots]).exclude(status='cancelled')} if can_bookings else {}
        days = []
        counts = {'free': 0, 'busy': 0, 'closed': 0}
        for offset, label in enumerate(('Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье')):
            day = week + timedelta(days=offset)
            items = []
            for slot in slots:
                if timezone.localdate(slot.starts_at) != day:
                    continue
                booking = bookings.get(slot.pk)
                if slot.active_booking_id:
                    state = 'confirmed' if booking and booking.status == 'confirmed' else 'busy'
                    label_state = 'Подтверждено' if state == 'confirmed' else 'Занято'
                    counts['busy'] += 1
                elif slot.starts_at <= timezone.now():
                    state, label_state = 'past', 'Прошло'
                    counts['closed'] += 1
                elif not slot.is_published:
                    state, label_state = 'hidden', 'Скрыто'
                    counts['closed'] += 1
                elif slot.is_blocked:
                    state, label_state = 'closed', 'Закрыто'
                    counts['closed'] += 1
                else:
                    state, label_state = 'free', 'Свободно'
                    counts['free'] += 1
                items.append({'slot': slot, 'state': state, 'label': label_state, 'booking': booking})
            days.append({'date': day, 'label': label, 'slots': items, 'today': day == today})
        return TemplateResponse(request, 'admin/core/appointmentslot/calendar.html', {
            **self.admin_site.each_context(request), 'opts': self.model._meta, 'title': 'Расписание приёма',
            'week': week, 'week_end': week + timedelta(days=6), 'previous': week - timedelta(days=7),
            'next': week + timedelta(days=7), 'today': today, 'days': days, 'counts': counts,
            'can_add': self.has_add_permission(request), 'can_change': self.has_change_permission(request),
            'has_slots': bool(slots), 'has_demo': any(slot.is_demo for slot in slots),
        })

    def window_view(self, request, object_id=None):
        if object_id is None:
            if not self.has_add_permission(request):
                raise PermissionDenied
            slot = AppointmentSlot()
        else:
            slot = self.get_object(request, str(object_id))
            if not slot:
                raise Http404
            if not self.has_view_or_change_permission(request, slot):
                raise PermissionDenied
        editable = self.has_change_permission(request, slot) if slot.pk else self.has_add_permission(request)
        day = timezone.localdate(slot.starts_at) if slot.pk else parse_day(request.GET.get('day', timezone.localdate().isoformat()))
        week = monday(day)
        start, end = bounds(week)
        existing = AppointmentSlot.objects.filter(starts_at__gte=start, starts_at__lt=end)
        initial = {'starts_at': timezone.make_aware(datetime.combine(day, time(10))),
                   'is_demo': existing.exists() and not existing.filter(is_demo=False).exists()}
        if request.method == 'POST':
            if not editable:
                raise PermissionDenied
            with transaction.atomic():
                if slot.pk:
                    # Same first-write lock as reserve_slot: a concurrent reservation must finish before validation.
                    AppointmentSlot.objects.filter(pk=slot.pk).update(reservation_version=F('reservation_version') + 1)
                    slot = AppointmentSlot.objects.get(pk=slot.pk)
                form = WindowForm(request.POST, instance=slot)
                if form.is_valid():
                    saved = form.save()
                    if object_id:
                        self.log_change(request, saved, 'Изменено в календаре: ' + ', '.join(form.changed_data))
                    else:
                        self.log_addition(request, saved, 'Добавлено в календаре.')
                    self.message_user(request, 'Окно сохранено. Расписание на сайте обновлено.', messages.SUCCESS)
                    return redirect(self.calendar_url(monday(timezone.localdate(saved.starts_at))))
        else:
            form = WindowForm(instance=slot, initial=initial if not slot.pk else None)
        booking = slot.bookings.exclude(status='cancelled').first() if slot.pk else None
        booking_admin = self.admin_site._registry.get(BookingRequest)
        can_view_booking = booking_admin and booking_admin.has_view_or_change_permission(request, booking)
        can_change_booking = can_view_booking and booking_admin.has_change_permission(request, booking)
        template = ('admin/core/appointmentslot/window_panel.html' if request.GET.get('panel') == '1'
                    else 'admin/core/appointmentslot/window.html')
        return TemplateResponse(request, template, {**self.admin_site.each_context(request),
            'opts': self.model._meta, 'title': 'Изменить окно' if slot.pk else 'Добавить окно',
            'form': form, 'slot': slot, 'calendar_url': self.calendar_url(week),
            'form_url': request.path, 'booking': booking if can_view_booking else None,
            'occupied': bool(booking), 'editable': editable, 'can_change_booking': can_change_booking})

    @method_decorator(require_POST)
    def day_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied
        day = parse_day(request.POST.get('day'))
        operation = request.POST.get('operation')
        if operation not in ('open', 'close'):
            raise Http404
        start, _ = bounds(day)
        count = 0
        with transaction.atomic():
            for slot in AppointmentSlot.objects.filter(starts_at__gte=start,
                    starts_at__lt=start + timedelta(days=1), starts_at__gt=timezone.now()):
                AppointmentSlot.objects.filter(pk=slot.pk).update(
                    is_blocked=operation == 'close', reservation_version=F('reservation_version') + 1)
                self.log_change(request, slot, 'День закрыт для новых записей.' if operation == 'close' else 'День открыт для записей.')
                count += 1
        self.message_user(request, f'Обновлено окон: {count}. Брони сохранены; скрытые окна остаются скрытыми.')
        return redirect(self.calendar_url(monday(day)))

    def copy_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        source = monday(parse_day(request.GET.get('week', request.POST.get('week'))))
        form = CopyWeekForm(request.POST if request.method == 'POST' else None,
                            initial={'target': source + timedelta(days=7)})
        if request.method == 'POST' and form.is_valid():
            target = form.cleaned_data['target']
            if target == source:
                form.add_error('target', 'Выберите другую неделю.')
            else:
                start, end = bounds(source)
                originals = list(AppointmentSlot.objects.filter(starts_at__gte=start, starts_at__lt=end))
                count = skipped = 0
                try:
                    with transaction.atomic():
                        for old in originals:
                            when = old.starts_at + timedelta(days=(target - source).days)
                            if AppointmentSlot.objects.filter(starts_at=when).exists():
                                skipped += 1
                                continue
                            new = AppointmentSlot(starts_at=when, service=old.service,
                                duration_minutes=old.duration_minutes, is_demo=old.is_demo,
                                is_published=old.is_published, is_blocked=old.is_blocked)
                            new.full_clean()
                            new.save()
                            self.log_addition(request, new, 'Скопировано расписание недели без заявок и заметок.')
                            count += 1
                except ValidationError as exc:
                    form.add_error(None, 'Есть пересечение времени. Ничего не скопировано. ' + '; '.join(exc.messages))
                else:
                    self.message_user(request, f'Добавлено окон: {count}. Уже существовавших: {skipped}. Заявки и заметки не копируются.')
                    return redirect(self.calendar_url(target))
        return TemplateResponse(request, 'admin/core/appointmentslot/copy.html', {
            **self.admin_site.each_context(request), 'title': 'Повторить расписание недели',
            'form': form, 'week': source, 'calendar_url': self.calendar_url(source), 'opts': self.model._meta})
