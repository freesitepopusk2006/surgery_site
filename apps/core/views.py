from django.shortcuts import render
from django.urls import reverse

from .models import SiteSettings, HomePage, Case, PriceItem, Review


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
        'phone': site_settings.phone if site_settings and site_settings.phone else '+7 (999) 999-99-99',
        'cta_text': site_settings.cta_text if site_settings and site_settings.cta_text else 'Запись на приём',
    }
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
        'phone': site_settings.phone if site_settings and site_settings.phone else '+7 (999) 999-99-99',
        'cta_text': site_settings.cta_text if site_settings and site_settings.cta_text else 'Запись на приём',
    }
    return render(request, 'core/patients.html', context)