from datetime import timedelta

from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig
from django.urls import reverse
from django.utils import timezone


class OwnerAdminConfig(AdminConfig):
    default_site = 'apps.core.admin_site.OwnerAdminSite'


class OwnerAdminSite(AdminSite):
    enable_nav_sidebar = False
    index_template = 'admin/owner_index.html'
    site_header = 'Управление сайтом'
    site_title = 'Кабинет владельца'
    index_title = 'Главная'

    def can_view(self, request, model):
        registered = self._registry.get(model)
        return registered and registered.has_view_or_change_permission(request)

    def each_context(self, request):
        from .models import AppointmentSlot, BookingRequest, HomePage, SiteSettings, PatientPage, PriceItem
        context = super().each_context(request)
        navigation = [('Главная', reverse('admin:index'))]
        for model, title in ((AppointmentSlot, 'Расписание'), (BookingRequest, 'Заявки'),
                             (HomePage, 'Главная страница'), (PriceItem, 'Цены'),
                             (PatientPage, 'Материалы'), (SiteSettings, 'Настройки')):
            if self.can_view(request, model):
                navigation.append((title, reverse(f'admin:core_{model._meta.model_name}_changelist')))
        context['owner_navigation'] = navigation
        return context

    def index(self, request, extra_context=None):
        from .models import (AppointmentSlot, BookingRequest, Direction, DoctorFact, FAQItem,
                             HomePage, PatientCategory, PatientPage, PriceCategory, PriceItem,
                             ProcessStep, Qualification, Review, SitePage, SiteSettings, Case)
        now = timezone.now()
        context = {'title': 'Ваш сайт', 'content_groups': []}
        definitions = (
            ('Страницы и оформление', ((HomePage, 'Главная страница', 'Заголовки, фотографии и порядок показа разделов'),
                                      (SiteSettings, 'Контакты и настройки', 'Клиника, карта, мессенджеры и почта для заявок'))),
            ('Услуги и врач', ((Direction, 'Направления лечения', 'Карточки направлений и связанные услуги'),
                              (PriceCategory, 'Разделы прайса', 'Категории с услугами внутри'),
                              (PriceItem, 'Все цены', 'Стоимость, описание и публикация услуг'),
                              (DoctorFact, 'Факты о враче', 'Цифры и подписи в блоке врача'),
                              (Qualification, 'Образование', 'Квалификация и документы'),
                              (ProcessStep, 'Этапы обращения', 'Как проходит путь пациента'))),
            ('Материалы и доверие', ((PatientPage, 'Статьи и памятки', 'Тексты, иллюстрации и разделы статей'),
                                    (PatientCategory, 'Категории материалов', 'Группы статей для пациентов'),
                                    (Review, 'Отзывы', 'Отзывы пациентов и ссылки на источники'),
                                    (FAQItem, 'Вопросы и ответы', 'Короткие ответы на частые вопросы'),
                                    (Case, 'Клинические случаи', 'Изображения и описания случаев'),
                                    (SitePage, 'Документы', 'Политика конфиденциальности и согласие'))),
        )
        for title, items in definitions:
            cards = [{'title': label, 'description': description,
                      'url': reverse(f'admin:core_{model._meta.model_name}_changelist')}
                     for model, label, description in items if self.can_view(request, model)]
            if cards:
                context['content_groups'].append((title, cards))
        if self.can_view(request, BookingRequest):
            context['pending_count'] = BookingRequest.objects.filter(status='new').count()
            context['upcoming_bookings'] = BookingRequest.objects.filter(
                appointment_start__gte=now).exclude(status='cancelled').order_by('appointment_start')[:6]
            context['booking_url'] = reverse('admin:core_bookingrequest_changelist')
        if self.can_view(request, AppointmentSlot):
            slots = AppointmentSlot.objects.filter(starts_at__gte=now, starts_at__lt=now + timedelta(days=7))
            context['free_count'] = slots.filter(is_published=True, is_blocked=False).exclude(
                bookings__status__in=['new', 'contacted', 'closed', 'confirmed']).count()
            context['demo_schedule'] = slots.filter(is_demo=True).exists()
            context['calendar_url'] = reverse('admin:core_appointmentslot_calendar')
        return super().index(request, {**context, **(extra_context or {})})
