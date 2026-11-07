import re

from django import forms


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
