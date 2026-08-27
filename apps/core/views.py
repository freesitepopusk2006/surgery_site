from django.db import OperationalError, ProgrammingError
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from .models import SiteSettings, HomePage, Case, PriceItem, Review, PatientCategory, PatientPage


CONTACT_PHONE = '+7 499 394 34 52'
CONTACT_PHONE_HREF = '+74993943452'
CONTACT_TELEGRAM_URL = 'https://t.me/Opht_KutinIM'
CONTACT_WHATSAPP_URL = 'https://wa.me/74993943452'
CONTACT_MAX_URL = 'https://max.ru/u/f9LHodD0cOLrvB0ibZk95T51QLuO4dRf1jeg-4mAenQNMPsj4h0MNExk0QA'
LIST_ITEM_MAX_LENGTH = 240
SHOW_CASES_ON_HOME = False


def get_contact_context(site_settings):
    return {
        'phone': CONTACT_PHONE,
        'phone_href': CONTACT_PHONE_HREF,
        'telegram_url': CONTACT_TELEGRAM_URL,
        'whatsapp_url': CONTACT_WHATSAPP_URL,
        'max_url': CONTACT_MAX_URL,
    }


def get_site_settings():
    try:
        return SiteSettings.objects.defer('max_url').first()
    except (OperationalError, ProgrammingError):
        return None


def home_view(request):
    site_settings = get_site_settings()
    homepage = HomePage.objects.order_by('-created_at').first()

    cases = Case.objects.filter(is_published=True)[:5] if SHOW_CASES_ON_HOME else []
    price_items = PriceItem.objects.filter(is_active=True)
    reviews = Review.objects.filter(is_published=True, show_on_home=True)[:6]

    context = {
        'page_title': 'Главная',
        'site_settings': site_settings,
        'homepage': homepage,
        'show_cases': SHOW_CASES_ON_HOME,
        'cases': cases,
        'price_items': price_items,
        'reviews': reviews,
        'nav_links': [
            {'label': 'Обо мне', 'href': '/#about'},
            {'label': 'Услуги и цены', 'href': reverse('core:prices')},
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
        {'label': 'Услуги и цены', 'href': reverse('core:prices')},
        {'label': 'Отзывы', 'href': '/#reviews'},
        {'label': 'Пациентам', 'href': reverse('core:patients')},
    ]


def prices_view(request):
    site_settings = get_site_settings()
    price_items = PriceItem.objects.filter(is_active=True)

    context = {
        'page_title': 'Услуги и цены',
        'site_settings': site_settings,
        'price_items': price_items,
        'nav_links': get_nav_links(),
        'cta_text': site_settings.cta_text if site_settings and site_settings.cta_text else 'Запись на приём',
    }
    context.update(get_contact_context(site_settings))
    return render(request, 'core/prices.html', context)


def patients_view(request):
    site_settings = get_site_settings()
    patient_categories = PatientCategory.objects.filter(
        is_published=True,
        pages__is_published=True,
    ).prefetch_related('pages').distinct()

    context = {
        'page_title': 'Пациентам',
        'site_settings': site_settings,
        'patient_categories': patient_categories,
        'nav_links': get_nav_links(),
        'cta_text': site_settings.cta_text if site_settings and site_settings.cta_text else 'Запись на приём',
    }
    context.update(get_contact_context(site_settings))
    return render(request, 'core/patients.html', context)


def split_patient_text_blocks(value):
    blocks = []
    current = []

    for raw_line in str(value or '').replace('\r\n', '\n').split('\n'):
        line = raw_line.strip()
        if line:
            current.append(line)
            continue

        if current:
            blocks.append('\n'.join(current))
            current = []

    if current:
        blocks.append('\n'.join(current))

    return blocks


def is_patient_list_item(block):
    if '\n' in block:
        return False
    if len(block) > LIST_ITEM_MAX_LENGTH:
        return False
    if block.endswith(':'):
        return False
    return True


def render_patient_text(value):
    blocks = split_patient_text_blocks(value)
    rendered = []
    index = 0

    while index < len(blocks):
        block = blocks[index]
        previous = blocks[index - 1] if index else ''
        should_start_list = (
            is_patient_list_item(block)
            and (
                previous.endswith(':')
                or (
                    index + 1 < len(blocks)
                    and is_patient_list_item(blocks[index + 1])
                )
            )
        )

        if should_start_list:
            items = []
            while index < len(blocks) and is_patient_list_item(blocks[index]):
                items.append(blocks[index])
                index += 1
            list_items = ''.join(f'<li>{conditional_escape(item)}</li>' for item in items)
            rendered.append(f'<ul class="patient-bullet-list">{list_items}</ul>')
            continue

        paragraph = conditional_escape(block).replace('\n', '<br>')
        rendered.append(f'<p>{paragraph}</p>')
        index += 1

    return mark_safe('\n'.join(rendered))


def patient_page_detail_view(request, slug):
    site_settings = get_site_settings()
    patient_page = get_object_or_404(
        PatientPage.objects.select_related('category').prefetch_related('sections'),
        slug=slug,
        is_published=True,
        category__is_published=True,
    )
    sections = [
        {
            'id': section.id,
            'title': section.title,
            'content_html': render_patient_text(section.content),
        }
        for section in patient_page.sections.all()
    ]

    context = {
        'page_title': patient_page.title,
        'site_settings': site_settings,
        'patient_page': patient_page,
        'description_html': render_patient_text(patient_page.description),
        'sections': sections,
        'nav_links': get_nav_links(),
        'cta_text': site_settings.cta_text if site_settings and site_settings.cta_text else 'Запись на приём',
    }
    context.update(get_contact_context(site_settings))
    return render(request, 'core/patient_page_detail.html', context)
