import re
from datetime import datetime, timedelta

from django import forms
from django.utils import timezone


class BookingForm(forms.Form):
    name = forms.CharField(max_length=120, min_length=2)
    phone = forms.CharField(max_length=40)
    consent = forms.BooleanField(required=True)
    website = forms.CharField(required=False, max_length=255)

    def clean_name(self):
        value = ' '.join(self.cleaned_data['name'].split())
        if not any(char.isalpha() for char in value):
            raise forms.ValidationError('Укажите имя.')
        return value

    def clean_phone(self):
        value = self.cleaned_data['phone']
        if re.search(r'[^\d\s()+.\-]', value):
            raise forms.ValidationError('Проверьте номер телефона.')
        digits = re.sub(r'\D', '', value)
        if not 10 <= len(digits) <= 15 or len(set(digits)) == 1:
            raise forms.ValidationError('Укажите номер с кодом страны или города.')
        if len(digits) == 11 and digits.startswith('8'):
            digits = '7' + digits[1:]
        if len(digits) == 10:
            digits = '7' + digits
        return '+' + digits


class AppointmentBookingForm(BookingForm):
    email = forms.EmailField(max_length=254)
    slot = forms.IntegerField(min_value=1)


class SlotGenerationForm(forms.Form):
    start_date = forms.DateField(label='Первый день недели', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    weekdays = forms.MultipleChoiceField(label='Рабочие дни',
        choices=[(str(i), label) for i, label in enumerate(['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'])],
        initial=['0', '1', '2', '3', '4', '5'], widget=forms.CheckboxSelectMultiple)
    start_time = forms.TimeField(label='Начало приёма', initial='10:00', widget=forms.TimeInput(attrs={'type': 'time'}))
    end_time = forms.TimeField(label='Конец приёма', initial='16:00', widget=forms.TimeInput(attrs={'type': 'time'}))
    break_start = forms.TimeField(label='Перерыв с', required=False, initial='13:00', widget=forms.TimeInput(attrs={'type': 'time'}))
    break_end = forms.TimeField(label='Перерыв до', required=False, initial='14:00', widget=forms.TimeInput(attrs={'type': 'time'}))
    duration = forms.TypedChoiceField(label='Длительность окна', choices=[(n, f'{n} минут') for n in (15, 20, 30, 45, 60)], coerce=int, initial=30)
    service = forms.CharField(label='Услуга', max_length=180, initial='Консультация офтальмолога')
    is_demo = forms.BooleanField(label='Демонстрационное расписание', required=False, initial=True)
    is_published = forms.BooleanField(label='Показывать на сайте', required=False, initial=True)

    def clean(self):
        data = super().clean()
        day, start, end = (data.get(key) for key in ('start_date', 'start_time', 'end_time'))
        if day and day < timezone.localdate():
            self.add_error('start_date', 'Выберите сегодняшний или будущий день.')
        if start and end and start >= end:
            self.add_error('end_time', 'Конец приёма должен быть позже начала.')
        pause_start, pause_end = data.get('break_start'), data.get('break_end')
        if bool(pause_start) != bool(pause_end):
            raise forms.ValidationError('Укажите обе границы перерыва или оставьте обе пустыми.')
        if start and end and pause_start and pause_end and not start < pause_start < pause_end < end:
            raise forms.ValidationError('Перерыв должен находиться внутри времени приёма.')
        return data

    def slot_values(self):
        data = self.cleaned_data
        for offset in range(7):
            day = data['start_date'] + timedelta(days=offset)
            if str(day.weekday()) not in data['weekdays']:
                continue
            current = timezone.make_aware(datetime.combine(day, data['start_time']))
            end = timezone.make_aware(datetime.combine(day, data['end_time']))
            step = timedelta(minutes=data['duration'])
            while current + step <= end:
                in_break = data.get('break_start') and (
                    current.time() < data['break_end'] and (current + step).time() > data['break_start'])
                if current > timezone.now() and not in_break:
                    yield {'starts_at': current, 'duration_minutes': data['duration'], 'service': data['service'],
                        'is_demo': data['is_demo'], 'is_published': data['is_published']}
                current += step
