from datetime import timedelta
import mimetypes
from pathlib import Path

from django.conf import settings
from django.db.models import Prefetch, Q
from django.db import IntegrityError, OperationalError
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils._os import safe_join
from django.core.exceptions import SuspiciousFileOperation
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from django.middleware.csrf import get_token

from .content import render_content
from .forms import BookingForm, AppointmentBookingForm
from .appointments import SlotUnavailable, reserve_slot, schedule_data
from .models import (
    BookingRequest, Case, Direction, HomePage, PatientCategory, PatientPage, DoctorFact, FAQItem,
    PriceCategory, PriceItem, ProcessStep, Qualification, Review, SitePage, SiteSettings,
)
from .notifications import notify_booking


def published_prices():
    return PriceItem.objects.filter(is_active=True).filter(
        Q(category__isnull=True) | Q(category__is_published=True)
    ).select_related('category')


def home_view(request):
    home = HomePage.objects.order_by('-created_at', '-pk').first() or HomePage()
    featured_prices = published_prices().order_by('order', 'pk')
    service_groups = list(PriceCategory.objects.filter(is_published=True, show_on_home=True).prefetch_related(
        Prefetch('items', queryset=featured_prices, to_attr='visible_items')
    )) if home.show_services else []
    service_groups = [group for group in service_groups if group.visible_items][:8]
    featured_pages = PatientPage.objects.filter(is_published=True, category__is_published=True).select_related('category')
    if home.pk and home.featured_patient_pages.exists():
        featured_pages = featured_pages.filter(pk__in=home.featured_patient_pages.values('pk'))[:6]
    else:
        featured_pages = featured_pages[:3]
    return render(request, 'core/home.html', {
        'page_title': '',
        'directions': Direction.objects.filter(is_published=True).select_related('patient_page__category').prefetch_related(
            Prefetch('services', queryset=featured_prices, to_attr='public_services')) if home.show_directions else [],
        'service_groups': service_groups,
        'doctor_facts': DoctorFact.objects.filter(is_published=True) if home.show_about else [],
        'qualifications': Qualification.objects.filter(is_published=True) if home.show_about else [],
        'process_steps': ProcessStep.objects.filter(is_published=True) if home.show_process else [],
        'cases': Case.objects.filter(is_published=True)[:6] if home.show_cases else [],
        'price_items': published_prices().filter(show_on_home=True).order_by('order', 'pk')[:6] if home.show_prices else [],
        'reviews': Review.objects.filter(is_published=True, show_on_home=True)[:6] if home.show_reviews else [],
        'about_html': render_content(home.about_text),
        'featured_pages': featured_pages if home.show_patient_materials else [],
        'faq_items': [{'question': item.question, 'answer_html': render_content(item.answer)}
                      for item in FAQItem.objects.filter(is_published=True)] if home.show_faq else [],
    })


def prices_view(request):
    active = published_prices().order_by('order', 'pk')
    groups = list(PriceCategory.objects.filter(is_published=True).prefetch_related(
        Prefetch('items', queryset=active, to_attr='visible_items')
    ))
    groups = [group for group in groups if group.visible_items]
    return render(request, 'core/prices.html', {
        'page_title': 'Услуги и цены', 'price_groups': groups,
        'uncategorized_prices': active.filter(category__isnull=True),
        'has_prices': active.exists(), 'active_nav': 'prices',
    })


def patients_view(request):
    pages = PatientPage.objects.filter(is_published=True).order_by('order', 'pk')
    categories = PatientCategory.objects.filter(is_published=True).prefetch_related(
        Prefetch('pages', queryset=pages, to_attr='visible_pages')
    )
    return render(request, 'core/patients.html', {
        'page_title': 'Пациентам', 'active_nav': 'patients',
        'patient_categories': [category for category in categories if category.visible_pages],
    })


def patient_page_detail_view(request, slug):
    page = get_object_or_404(
        PatientPage.objects.select_related('category').prefetch_related('sections'),
        slug=slug, is_published=True, category__is_published=True,
    )
    sections = [{'id': part.pk, 'title': part.title, 'content_html': render_content(part.content)}
                for part in page.sections.all()]
    related = PatientPage.objects.filter(category=page.category, is_published=True).exclude(pk=page.pk)[:3]
    return render(request, 'core/patient_page_detail.html', {
        'page_title': page.title, 'page_description': page.seo_description or page.description[:280],
        'patient_page': page, 'description_html': render_content(page.description),
        'sections': sections, 'related_pages': related, 'active_nav': 'patients',
    })


def site_page_view(request, slug):
    page = get_object_or_404(SitePage, slug=slug, is_published=True)
    return render(request, 'core/site_page.html', {
        'page_title': page.title, 'page_description': page.seo_description,
        'document': page, 'body_html': render_content(page.body),
    })


@require_POST
def booking_view(request):
    if int(request.META.get('CONTENT_LENGTH') or 0) > 8192:
        return JsonResponse({'ok': False, 'error': 'Слишком большой запрос.'}, status=413)
    site = SiteSettings.objects.order_by('pk').first()
    privacy = SitePage.objects.filter(slug='privacy', is_published=True).exists()
    consent = SitePage.objects.filter(slug='consent', is_published=True).first()
    if not site or not site.booking_enabled or not consent or not (privacy or site.privacy_policy_url):
        return JsonResponse({'ok': False, 'error': 'Онлайн-запись пока недоступна. Используйте контакты на сайте.'}, status=503)
    form = BookingForm(request.POST)
    if not form.is_valid():
        messages = {
            'name': 'Укажите имя длиной от 2 до 120 символов.',
            'phone': 'Проверьте номер телефона.',
            'consent': 'Подтвердите согласие на обработку данных.',
        }
        return JsonResponse({'ok': False, 'errors': {key: messages.get(key, 'Проверьте поле.') for key in form.errors}}, status=400)
    if form.cleaned_data['website']:
        return JsonResponse({'ok': False, 'error': 'Не удалось отправить форму.'}, status=400)
    # Use only the trusted direct peer address; never trust a client-supplied forwarded-for header.
    peer = request.META.get('REMOTE_ADDR', '')
    throttle = salted_hmac('booking-peer', peer, secret=settings.SECRET_KEY).hexdigest()
    recent = BookingRequest.objects.filter(created_at__gte=timezone.now() - timedelta(minutes=10))
    duplicate = recent.filter(phone=form.cleaned_data['phone'], throttle_key=throttle).first()
    if duplicate:
        return JsonResponse({'ok': True})
    if recent.filter(throttle_key=throttle).count() >= settings.BOOKING_RATE_LIMIT:
        return JsonResponse({'ok': False, 'error': 'Слишком много заявок. Попробуйте немного позже или позвоните.'}, status=429)
    booking = BookingRequest.objects.create(
        name=form.cleaned_data['name'], phone=form.cleaned_data['phone'], consent=True,
        consent_document=consent.get_absolute_url(), throttle_key=throttle,
    )
    # The request is durable before attempting an external notification.
    notify_booking(booking, site_url=request.build_absolute_uri('/'))
    return JsonResponse({'ok': True}, status=201)


def appointment_slots_view(request):
    site = SiteSettings.objects.order_by('pk').first()
    if not site or not site.booking_enabled or not site.schedule_enabled:
        return JsonResponse({'error': 'Расписание пока недоступно.'}, status=503)
    try:
        result = schedule_data(site, request.GET.get('week'))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Выберите неделю в пределах ближайших трёх месяцев.'}, status=400)
    response = JsonResponse(result)
    response['Cache-Control'] = 'no-store'
    return response


@require_GET
def booking_csrf_view(request):
    response = JsonResponse({'csrfToken': get_token(request)})
    response['Cache-Control'] = 'no-store'
    return response


def csrf_failure_view(request, reason=''):
    if request.path.startswith('/booking/'):
        return JsonResponse({'ok': False, 'csrf_error': True,
            'error': 'Сессия формы обновилась. Повторите отправку; введённые данные сохранены.'}, status=403)
    from django.views.csrf import csrf_failure
    return csrf_failure(request, reason=reason)


@require_POST
def appointment_booking_view(request):
    if int(request.META.get('CONTENT_LENGTH') or 0) > 8192:
        return JsonResponse({'ok': False, 'error': 'Слишком большой запрос.'}, status=413)
    site = SiteSettings.objects.order_by('pk').first()
    if not site or not site.booking_enabled or not site.schedule_enabled:
        return JsonResponse({'ok': False, 'error': 'Запись пока недоступна.'}, status=503)
    form = AppointmentBookingForm(request.POST)
    if not form.is_valid():
        messages = {'name': 'Укажите ФИО.', 'phone': 'Проверьте номер телефона.',
            'email': 'Укажите корректную почту.', 'consent': 'Подтвердите согласие.', 'slot': 'Выберите время.'}
        return JsonResponse({'ok': False, 'errors': {key: messages.get(key, 'Проверьте поле.') for key in form.errors}}, status=400)
    if form.cleaned_data['website']:
        return JsonResponse({'ok': False, 'error': 'Не удалось забронировать время.'}, status=400)
    throttle = salted_hmac('booking-peer', request.META.get('REMOTE_ADDR', ''), secret=settings.SECRET_KEY).hexdigest()
    recent = BookingRequest.objects.filter(created_at__gte=timezone.now() - timedelta(minutes=10))
    duplicate = recent.filter(slot_id=form.cleaned_data['slot'], phone=form.cleaned_data['phone'],
        email__iexact=form.cleaned_data['email'], name=form.cleaned_data['name'], throttle_key=throttle).exclude(status='cancelled').first()
    if duplicate:
        return JsonResponse({'ok': True, 'booking_id': duplicate.pk, 'demo': duplicate.is_demo})
    if recent.filter(throttle_key=throttle).count() >= settings.BOOKING_RATE_LIMIT:
        return JsonResponse({'ok': False, 'error': 'Слишком много заявок. Попробуйте позже или позвоните.'}, status=429)
    try:
        booking = reserve_slot(form.cleaned_data['slot'], form.cleaned_data, throttle, site)
    except (SlotUnavailable, IntegrityError, OperationalError):
        return JsonResponse({'ok': False, 'conflict': True,
            'error': 'Это время уже занято или закрыто. Обновите расписание и выберите другое окно.'}, status=409)
    notify_booking(booking, site_url=request.build_absolute_uri('/'))
    return JsonResponse({'ok': True, 'booking_id': booking.pk, 'demo': booking.is_demo}, status=201)


def robots_view(request):
    return HttpResponse('User-agent: *\nDisallow: /admin/\nDisallow: /booking/\nSitemap: '
                        + request.build_absolute_uri(reverse('core:sitemap')) + '\n', content_type='text/plain')


def sitemap_view(request):
    paths = [reverse('core:home'), reverse('core:prices'), reverse('core:patients')]
    paths.extend(page.get_absolute_url() for page in PatientPage.objects.filter(is_published=True, category__is_published=True))
    paths.extend(page.get_absolute_url() for page in SitePage.objects.filter(is_published=True))
    return render(request, 'core/sitemap.xml', {'urls': [request.build_absolute_uri(path) for path in paths]},
                  content_type='application/xml')


def not_found_view(request, exception):
    return render(request, 'core/404.html', {'page_title': 'Страница не найдена'}, status=404)


def health_view(request):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return JsonResponse({'status': 'ok'})


def media_view(request, path):
    """Public images and approved PDF documents, including after DEBUG is disabled."""
    try:
        file_path = Path(safe_join(settings.MEDIA_ROOT, path))
    except SuspiciousFileOperation as exc:
        raise Http404 from exc
    if file_path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif', '.pdf', '.ico'} or not file_path.is_file():
        raise Http404
    response = FileResponse(file_path.open('rb'), content_type=mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream')
    response['Cache-Control'] = 'public, max-age=86400'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
