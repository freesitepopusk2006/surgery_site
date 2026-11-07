from django.urls import reverse

from .models import Direction, DoctorFact, HomePage, Qualification, Review, SitePage, SiteSettings


def site_context(request):
    site = SiteSettings.objects.order_by('pk').first() or SiteSettings()
    home = HomePage.objects.order_by('-created_at').first() or HomePage()
    documents = list(SitePage.objects.filter(is_published=True).only('title', 'slug'))
    by_slug = {page.slug: page for page in documents}
    privacy_url = site.privacy_policy_url or (
        by_slug['privacy'].get_absolute_url() if 'privacy' in by_slug else ''
    )
    consent_url = by_slug['consent'].get_absolute_url() if 'consent' in by_slug else ''
    has_about = home.show_about and bool(home.show_placeholders or home.about_text or home.about_photo or Qualification.objects.filter(is_published=True).exists() or DoctorFact.objects.filter(is_published=True).exists())
    has_directions = home.show_directions and (home.show_placeholders or Direction.objects.filter(is_published=True).exists())
    has_reviews = home.show_reviews and (home.show_placeholders or Review.objects.filter(is_published=True, show_on_home=True).exists())
    has_clinic = home.show_clinic and bool(home.show_placeholders or site.address or site.clinic_name or home.clinic_photo or home.clinic_description)
    nav = []
    if has_about:
        nav.append({'label': 'О враче', 'href': reverse('core:home') + '#about', 'key': 'about'})
    if has_directions:
        nav.append({'label': 'Направления', 'href': reverse('core:home') + '#directions', 'key': 'directions'})
    nav.extend([
        {'label': 'Услуги и цены', 'href': reverse('core:prices'), 'key': 'prices'},
        {'label': site.patients_title, 'href': reverse('core:patients'), 'key': 'patients'},
    ])
    if has_reviews:
        nav.append({'label': 'Отзывы', 'href': reverse('core:home') + '#reviews', 'key': 'reviews'})
    phone_href = ''.join(c for c in site.phone if c.isdigit() or c == '+')
    social_links = [
        {'label': label, 'url': url} for label, url in [
            ('Telegram', site.telegram_url), ('WhatsApp', site.whatsapp_url),
            ('Max', site.max_url), ('VK', site.vk_url),
        ] if url
    ]
    return {
        'site_settings': site, 'homepage': home,
        'brand_name': site.short_name or site.doctor_name or 'Офтальмология',
        'phone_href': phone_href, 'social_links': social_links, 'nav_links': nav,
        'privacy_url': privacy_url, 'consent_url': consent_url, 'site_documents': documents,
        'booking_available': bool(site.pk and site.booking_enabled and privacy_url and consent_url),
        'has_about': has_about, 'has_directions': has_directions,
        'has_reviews': has_reviews, 'has_clinic': has_clinic,
        'canonical_url': request.build_absolute_uri(request.path),
    }
