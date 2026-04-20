from django.shortcuts import render
from django.urls import reverse

from .models import SiteSettings, HomePage, Case, PriceItem, Review


CONTACT_PHONE = '+7 499 394 34 52'
CONTACT_PHONE_HREF = '+74993943452'
CONTACT_TELEGRAM_URL = 'https://t.me/Opht_KutinIM'
CONTACT_WHATSAPP_URL = 'https://wa.me/74993943452'
CONTACT_MAX_URL = 'https://max.ru/u/f9LHodD0cOLrvB0ibZk95T51QLuO4dRf1jeg-4mAenQNMPsj4h0MNExk0QA'


def get_contact_context(site_settings):
    return {
        'phone': CONTACT_PHONE,
        'phone_href': CONTACT_PHONE_HREF,
        'telegram_url': CONTACT_TELEGRAM_URL,
        'whatsapp_url': CONTACT_WHATSAPP_URL,
        'max_url': CONTACT_MAX_URL,
    }


def home_view(request):
    site_settings = SiteSettings.objects.first()
    homepage = HomePage.objects.order_by('-created_at').first()

    cases = Case.objects.filter(is_published=True)[:5]
    price_items = PriceItem.objects.filter(is_active=True)
    reviews = Review.objects.filter(is_published=True, show_on_home=True)[:6]

    context = {
        'page_title': 'Главная',
        'site_settings': site_settings,
        'homepage': homepage,
        'cases': cases,
        'price_items': price_items,
        'reviews': reviews,
        'nav_links': [
            {'label': 'Обо мне', 'href': '/#about'},
            {'label': 'Отзывы', 'href': '/#reviews'},
            {'label': 'Пациентам', 'href': reverse('core:patients')},
        ],
        'cta_text': site_settings.cta_text if site_settings and site_settings.cta_text else 'Запись на приём',
    }
    context.update(get_contact_context(site_settings))
    return render(request, 'core/home.html', context)


def get_nav_links():
    return [
        {'label': 'Обо мне', 'href': '/#about'},
        {'label': 'Отзывы', 'href': '/#reviews'},
        {'label': 'Пациентам', 'href': reverse('core:patients')},
    ]


def patients_view(request):
    site_settings = SiteSettings.objects.first()

    context = {
        'page_title': 'Пациентам',
        'site_settings': site_settings,
        'nav_links': get_nav_links(),
        'cta_text': site_settings.cta_text if site_settings and site_settings.cta_text else 'Запись на приём',
    }
    context.update(get_contact_context(site_settings))
    return render(request, 'core/patients.html', context)
