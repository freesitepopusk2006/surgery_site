from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .content import render_content
from .models import (
    BookingRequest, Direction, HomePage, PatientCategory, PatientPage, PatientPageSection,
    PriceCategory, PriceItem, ProcessStep, Qualification, Review, SitePage, SiteSettings, DoctorFact, FAQItem,
)
from .notifications import notify_booking
from .validators import validate_map_embed_url
from django.core.exceptions import ValidationError


class EditorialPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = SiteSettings.objects.create(doctor_name='Тестовый врач', phone='+7 000 111-22-33',
            telegram_url='https://t.me/test_account', address='Тестовый адрес')
        cls.home = HomePage.objects.create(hero_title='Редактируемый заголовок', hero_intro='Редактируемое введение',
            about_text='Биография из админки', clinic_description='Описание клиники из админки')
        cls.category = PatientCategory.objects.create(title='Тестовая категория', slug='тестовая-категория')
        cls.page = PatientPage.objects.create(category=cls.category, title='Опубликованная статья', slug='статья',
            description='Вводный текст', author_name='Автор из админки')
        PatientPageSection.objects.create(page=cls.page, title='Раздел статьи', content='Текст раздела.\n\n- Первый пункт\n- Второй пункт')
        cls.draft = PatientPage.objects.create(category=cls.category, title='Скрытая статья', slug='draft', is_published=False)
        cls.hidden_category = PatientCategory.objects.create(title='Скрытая категория', slug='hidden', is_published=False)
        cls.hidden_page = PatientPage.objects.create(category=cls.hidden_category, title='Скрытый раздел', slug='hidden-page')
        cls.price_category = PriceCategory.objects.create(title='Категория услуг', unit_text='За оба глаза')
        cls.price = PriceItem.objects.create(category=cls.price_category, title='Тестовая услуга', price_text='10 000 ₽',
            description='Описание цены', unit_text='За один глаз', show_on_home=True)
        cls.inactive_price = PriceItem.objects.create(title='Неактивная цена', is_active=False)
        hidden_prices = PriceCategory.objects.create(title='Скрытый прайс', is_published=False)
        PriceItem.objects.create(category=hidden_prices, title='Цена скрытой категории', show_on_home=True)
        Direction.objects.create(title='Направление из админки', description='Описание направления', patient_page=cls.page)
        ProcessStep.objects.create(title='Этап из админки', description='Описание этапа')
        Qualification.objects.create(title='Подтверждённая квалификация')
        Review.objects.create(patient_name='Тестовый автор', text='Тестовый отзыв', source_url='https://example.com/review')
        SitePage.objects.create(title='Политика', slug='privacy', body='Тестовый текст политики', is_published=True)
        SitePage.objects.create(title='Согласие', slug='consent', body='Тестовый текст согласия', is_published=True)

    def test_complete_home_uses_admin_content(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        for text in ['Редактируемый заголовок', 'Биография из админки', 'Направление из админки',
                     'Этап из админки', 'Тестовая услуга', 'Тестовый отзыв', 'Описание клиники из админки']:
            self.assertContains(response, text)
        self.assertNotContains(response, '+7 499 394 34 52')
        self.assertNotContains(response, 'Цена скрытой категории')
        self.assertContains(response, 'id="bookingForm"')

    def test_changes_in_admin_data_are_reflected(self):
        self.site.phone = '+7 000 999-88-77'
        self.site.save()
        response = self.client.get('/patients/')
        self.assertContains(response, '+7 000 999-88-77')
        self.assertNotContains(response, '+7 000 111-22-33')

    def test_disabled_sections_and_navigation_are_hidden(self):
        self.home.show_about = False
        self.home.show_directions = False
        self.home.show_reviews = False
        self.home.save()
        response = self.client.get('/')
        self.assertNotContains(response, 'id="about"')
        self.assertNotContains(response, 'id="directions"')
        self.assertNotContains(response, 'id="reviews"')
        self.assertNotContains(response, 'href="/#about"')

    def test_prices_respect_visibility_and_units(self):
        response = self.client.get('/prices/')
        self.assertContains(response, 'Категория услуг')
        self.assertContains(response, 'За один глаз')
        self.assertNotContains(response, 'Неактивная цена')
        self.assertNotContains(response, 'Цена скрытой категории')
        self.price.unit_text = ''
        self.assertEqual(self.price.unit_label, 'За оба глаза')

    def test_uncategorized_price_renders_without_description(self):
        PriceItem.objects.create(title='Услуга без категории', price_text='от 5 000 ₽')
        response = self.client.get('/prices/')
        self.assertContains(response, 'Услуга без категории')

    def test_patient_directory_does_not_disclose_unpublished_items(self):
        response = self.client.get('/patients/')
        self.assertContains(response, 'Опубликованная статья')
        self.assertNotContains(response, 'Скрытая статья')
        self.assertNotContains(response, 'Скрытая категория')

    def test_unicode_article_and_no_image_placeholder(self):
        response = self.client.get(self.page.get_absolute_url())
        self.assertContains(response, 'Раздел статьи')
        self.assertContains(response, '<li>Первый пункт</li>', html=True)
        self.assertNotContains(response, 'Основная картинка')
        self.assertNotContains(response, 'class="article-image"')

    def test_unpublished_article_and_category_return_404(self):
        for page in [self.draft, self.hidden_page]:
            self.assertEqual(self.client.get(page.get_absolute_url()).status_code, 404)

    def test_direction_does_not_link_to_unpublished_article(self):
        direction = Direction.objects.create(title='Связь с черновиком', patient_page=self.draft)
        self.assertEqual(direction.link, '')

    def test_policy_and_sitemap(self):
        self.assertContains(self.client.get('/privacy/'), 'Тестовый текст политики')
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.page.get_absolute_url())
        self.assertNotContains(response, self.draft.get_absolute_url())
        self.assertNotContains(response, self.hidden_page.get_absolute_url())

    @override_settings(DEBUG=False, STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
    def test_custom_404_and_media_in_production(self):
        self.assertContains(self.client.get('/missing-page/'), 'Ошибка 404', status_code=404)
        with TemporaryDirectory() as directory:
            Path(directory, 'sample.png').write_bytes(b'\x89PNG\r\n\x1a\n')
            Path(directory, 'unsafe.html').write_text('<script>bad()</script>')
            with override_settings(MEDIA_ROOT=directory):
                response = self.client.get('/media/sample.png')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'image/png')
                response.close()
                self.assertEqual(self.client.get('/media/unsafe.html').status_code, 404)
                self.assertEqual(self.client.get('/media/../settings.py').status_code, 404)


class EmptySiteTests(TestCase):
    def test_empty_site_renders_without_fake_content(self):
        for url in ['/', '/prices/', '/patients/']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            for placeholder in ['Здесь будет', 'Имя Фамилия', 'Название кейса', 'добавьте через админку']:
                self.assertNotContains(response, placeholder)
            self.assertNotContains(response, 'id="bookingForm"')

    def test_home_keeps_the_full_enabled_structure_before_content_is_added(self):
        HomePage.objects.create(show_cases=True)
        response = self.client.get('/')
        for section in ['directions', 'services', 'about', 'approach', 'cases', 'clinic', 'prices', 'reviews', 'patient-materials', 'faq']:
            self.assertContains(response, f'id="{section}"')
        self.assertNotContains(response, 'Тестовый отзыв')
        self.assertNotContains(response, 'Имя Фамилия')

    def test_scaffolds_can_be_disabled_without_erasing_data(self):
        HomePage.objects.create(show_placeholders=False, show_cases=True)
        response = self.client.get('/')
        for section in ['directions', 'services', 'about', 'approach', 'cases', 'clinic', 'prices', 'reviews', 'patient-materials', 'faq']:
            self.assertNotContains(response, f'id="{section}"')


class HomeStructureTests(TestCase):
    def setUp(self):
        self.home = HomePage.objects.create(show_placeholders=False)
        self.group = PriceCategory.objects.create(title='Группа вариантов')
        self.visible = PriceItem.objects.create(category=self.group, title='Опубликованный вариант', price_text='10 000 ₽')
        self.hidden = PriceItem.objects.create(category=self.group, title='Скрытый вариант', is_active=False)
        self.direction = Direction.objects.create(title='Динамическое направление', presentation='expandable')
        self.direction.services.add(self.visible, self.hidden)

    def test_direction_expands_only_published_service_variants(self):
        response = self.client.get('/')
        self.assertContains(response, 'class="direction-expandable"')
        self.assertContains(response, 'Опубликованный вариант')
        self.assertNotContains(response, 'Скрытый вариант')
        self.group.is_published = False
        self.group.save()
        response = self.client.get('/')
        self.assertNotContains(response, 'Опубликованный вариант')

    def test_category_can_be_hidden_from_home_without_hiding_price_page(self):
        self.direction.services.clear()
        self.group.show_on_home = False
        self.group.save()
        self.assertNotContains(self.client.get('/'), 'id="services"')
        self.assertContains(self.client.get('/prices/'), 'Группа вариантов')

    def test_published_facts_and_faq_are_rendered_from_admin(self):
        DoctorFact.objects.create(title='Профиль', value='Данные из админки')
        FAQItem.objects.create(question='Опубликованный вопрос?', answer='- Первый пункт\n- Второй пункт')
        FAQItem.objects.create(question='Черновой вопрос?', answer='Черновик', is_published=False)
        response = self.client.get('/')
        self.assertContains(response, 'id="about"')
        self.assertContains(response, 'Данные из админки')
        self.assertContains(response, 'Опубликованный вопрос?')
        self.assertContains(response, '<li>Первый пункт</li>', html=True)
        self.assertNotContains(response, 'Черновой вопрос?')

    def test_home_only_displays_selected_published_patient_materials(self):
        category = PatientCategory.objects.create(title='Материалы', slug='materials')
        selected = PatientPage.objects.create(category=category, title='Выбранная статья', slug='chosen')
        other = PatientPage.objects.create(category=category, title='Другая статья', slug='other')
        draft = PatientPage.objects.create(category=category, title='Выбранный черновик', slug='chosen-draft', is_published=False)
        self.home.featured_patient_pages.add(selected, draft)
        response = self.client.get('/')
        self.assertContains(response, 'Выбранная статья')
        self.assertNotContains(response, 'Другая статья')
        self.assertNotContains(response, 'Выбранный черновик')


class BookingTests(TestCase):
    def setUp(self):
        self.site = SiteSettings.objects.create(notification_email='test@example.com')
        SitePage.objects.create(title='Политика', slug='privacy', body='Тест', is_published=True)
        SitePage.objects.create(title='Согласие', slug='consent', body='Тест', is_published=True)
        self.payload = {'name': 'Тестовое имя', 'phone': '8 (900) 123-45-67', 'consent': 'on', 'website': ''}

    def test_saves_before_notification_and_normalizes_phone(self):
        def notification(booking):
            self.assertTrue(BookingRequest.objects.filter(pk=booking.pk).exists())
        with patch('apps.core.views.notify_booking', side_effect=notification) as notify:
            response = self.client.post('/booking/', self.payload)
        self.assertEqual(response.status_code, 201)
        request = BookingRequest.objects.get()
        self.assertEqual(request.phone, '+79001234567')
        self.assertTrue(request.consent)
        self.assertEqual(request.consent_document, '/pages/consent/')
        notify.assert_called_once()

    def test_invalid_phone_and_missing_consent_are_not_saved(self):
        for update in [{'phone': 'abc'}, {'phone': '11111111111'}, {'consent': ''}, {'name': '12'}]:
            response = self.client.post('/booking/', {**self.payload, **update})
            self.assertEqual(response.status_code, 400)
        self.assertFalse(BookingRequest.objects.exists())

    def test_csrf_is_required(self):
        response = Client(enforce_csrf_checks=True).post('/booking/', self.payload)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BookingRequest.objects.exists())

    def test_document_or_setting_can_disable_booking(self):
        SitePage.objects.filter(slug='consent').update(is_published=False)
        self.assertEqual(self.client.post('/booking/', self.payload).status_code, 503)
        self.assertFalse(BookingRequest.objects.exists())

    @patch('apps.core.views.notify_booking')
    def test_repeat_submission_does_not_duplicate(self, notify):
        self.client.post('/booking/', self.payload)
        self.assertEqual(self.client.post('/booking/', self.payload).status_code, 200)
        self.assertEqual(BookingRequest.objects.count(), 1)
        notify.assert_called_once()

    @override_settings(BOOKING_RATE_LIMIT=3)
    @patch('apps.core.views.notify_booking')
    def test_rate_limit_applies_to_multiple_numbers(self, notify):
        for index in range(3):
            self.assertEqual(self.client.post('/booking/', {**self.payload, 'phone': f'+7900123456{index}'}).status_code, 201)
        self.assertEqual(self.client.post('/booking/', {**self.payload, 'phone': '+79001234569'}).status_code, 429)
        self.assertEqual(BookingRequest.objects.count(), 3)

    def test_honeypot_rejects_automated_submission(self):
        self.assertEqual(self.client.post('/booking/', {**self.payload, 'website': 'spam'}).status_code, 400)
        self.assertFalse(BookingRequest.objects.exists())

    @override_settings(RESEND_API_KEY='test-key-not-real', DEFAULT_FROM_EMAIL='sender@example.com')
    def test_notification_failure_keeps_saved_request(self):
        with patch('apps.core.notifications.urlopen', side_effect=URLError('test network failure')):
            response = self.client.post('/booking/', self.payload)
        self.assertEqual(response.status_code, 201)
        booking = BookingRequest.objects.get()
        self.assertEqual(booking.notification_status, BookingRequest.Notification.FAILED)

    @override_settings(RESEND_API_KEY='', DEFAULT_FROM_EMAIL='')
    def test_unconfigured_mail_is_visible_to_admin(self):
        self.client.post('/booking/', self.payload)
        self.assertEqual(BookingRequest.objects.get().notification_status, BookingRequest.Notification.UNCONFIGURED)

    @override_settings(RESEND_API_KEY='test-key-not-real', DEFAULT_FROM_EMAIL='sender@example.com')
    def test_notification_success(self):
        booking = BookingRequest.objects.create(name='Тест', phone='+79001234567', consent=True)
        response = Mock(status=200)
        response.read.return_value = b'{"id":"test-message"}'
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch('apps.core.notifications.urlopen', return_value=context):
            self.assertEqual(notify_booking(booking), BookingRequest.Notification.SENT)


class AdminTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(username='test-admin', password='test-password-only')
        self.client.force_login(user)

    def test_settings_redirect_to_single_form(self):
        first = SiteSettings.objects.create(doctor_name='Основная запись')
        SiteSettings.objects.create(doctor_name='Архивная запись')
        self.assertRedirects(self.client.get(reverse('admin:core_sitesettings_changelist')),
                             reverse('admin:core_sitesettings_change', args=[first.pk]))
        self.assertEqual(self.client.get(reverse('admin:core_sitesettings_add')).status_code, 403)

    def test_home_redirects_to_current_record_without_deleting_archive(self):
        HomePage.objects.create(hero_title='Архив')
        current = HomePage.objects.create(hero_title='Текущая')
        self.assertRedirects(self.client.get(reverse('admin:core_homepage_changelist')),
                             reverse('admin:core_homepage_change', args=[current.pk]))
        self.assertEqual(HomePage.objects.count(), 2)

    def test_all_new_admin_forms_render(self):
        for model in ['direction', 'processstep', 'qualification', 'pricecategory', 'sitepage', 'priceitem', 'doctorfact', 'faqitem']:
            self.assertEqual(self.client.get(reverse(f'admin:core_{model}_add')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:core_bookingrequest_changelist')).status_code, 200)


class ContentFormattingTests(TestCase):
    def test_plain_paragraphs_are_not_turned_into_lists(self):
        self.assertEqual(str(render_content('Первый абзац.\n\nВторой абзац.')), '<p>Первый абзац.</p>\n<p>Второй абзац.</p>')

    def test_html_is_escaped_and_explicit_lists_are_preserved(self):
        result = str(render_content('## Заголовок\n\n- Первый\n- <script>bad()</script>'))
        self.assertIn('<h3>Заголовок</h3>', result)
        self.assertIn('<li>Первый</li>', result)
        self.assertIn('&lt;script&gt;', result)
        self.assertNotIn('<script>', result)


class ClinicMapTests(TestCase):
    def setUp(self):
        self.map_url = 'https://yandex.ru/map-widget/v1/?ll=37.1%2C55.1&z=16'
        self.site = SiteSettings.objects.create(address='Адрес из админки', map_embed_url=self.map_url,
            contact_email='public@example.com', notification_email='private@example.com')
        HomePage.objects.create(show_placeholders=False)

    def test_map_uses_admin_url_and_address(self):
        response = self.client.get('/')
        self.assertContains(response, 'class="clinic-map"')
        self.assertContains(response, 'https://yandex.ru/map-widget/v1/?ll=37.1%2C55.1&amp;z=16')
        self.assertContains(response, 'Карта проезда: Адрес из админки')

    def test_disabled_or_empty_map_does_not_create_an_empty_frame(self):
        self.site.show_map = False
        self.site.save()
        self.assertNotContains(self.client.get('/'), '<iframe')
        self.site.show_map = True
        self.site.map_embed_url = ''
        self.site.save()
        self.assertNotContains(self.client.get('/'), '<iframe')

    def test_untrusted_embed_urls_are_rejected(self):
        for value in ['javascript:alert(1)', 'http://yandex.ru/map-widget/v1/',
                      'https://yandex.ru.evil.example/map-widget/v1/',
                      'https://example.com/', 'https://user:password@yandex.ru/map-widget/v1/',
                      '<iframe src="https://yandex.ru/map-widget/v1/"></iframe>']:
            with self.assertRaises(ValidationError):
                validate_map_embed_url(value)
        validate_map_embed_url(self.map_url)
        validate_map_embed_url('https://www.google.com/maps/embed?pb=test')

    def test_invalid_database_value_is_not_rendered(self):
        SiteSettings.objects.filter(pk=self.site.pk).update(map_embed_url='https://example.com/')
        self.assertNotContains(self.client.get('/'), '<iframe')

    def test_public_contact_email_never_discloses_notification_email(self):
        response = self.client.get('/')
        self.assertContains(response, 'mailto:public@example.com')
        self.assertNotContains(response, 'private@example.com')
