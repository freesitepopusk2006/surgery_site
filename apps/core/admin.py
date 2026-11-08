from django.contrib import admin, messages
from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from datetime import timedelta
from datetime import datetime
from django.http import Http404
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from .models import (
    SiteSettings,
    HomePage,
    Case,
    PriceItem,
    Review,
    PatientCategory,
    PatientPage,
    PatientPageSection,
    Direction, ProcessStep, Qualification, PriceCategory, SitePage, BookingRequest, DoctorFact, FAQItem, AppointmentSlot,
)
from .forms import SlotGenerationForm
from .admin_schedule import OwnerScheduleMixin, monday
from django.template.response import TemplateResponse


class ExistingImageFormMixin:
    def _keep_existing_image(self, field_name):
        value = self.cleaned_data.get(field_name)
        if value is False:
            return value
        if value:
            return value
        if self.instance and self.instance.pk:
            return getattr(self.instance, field_name)
        return value


class SiteSettingsAdminForm(ExistingImageFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        wording = {
            'notification_email': ('Куда присылать новые заявки', 'Личная почта получателя. Посетители сайта её не видят.'),
            'contact_email': ('Почта для посетителей', 'Публичный адрес: показывается на сайте рядом с контактами.'),
            'map_url': ('Ссылка «Построить маршрут»', 'Скопируйте ссылку на клинику из Яндекс Карт или другого сервиса.'),
            'map_embed_url': ('Ссылка для интерактивной карты', 'Вставьте только адрес из src карты, без кода iframe.'),
            'cta_text': ('Текст кнопки записи', 'Короткая надпись на основной кнопке сайта.'),
            'booking_enabled': ('Принимать заявки с сайта', 'Заявки сохраняются в кабинете. Уведомления отправляются на вашу почту.'),
            'schedule_enabled': ('Показывать запись по времени', 'Сами дни и часы меняются в разделе «Расписание».'),
        }
        for name, (label, help_text) in wording.items():
            if name in self.fields:
                self.fields[name].label, self.fields[name].help_text = label, help_text

    def clean_logo(self):
        return self._keep_existing_image('logo')


class HomePageAdminForm(ExistingImageFormMixin, forms.ModelForm):
    def clean_hero_background(self):
        return self._keep_existing_image('hero_background')

    def clean_about_photo(self):
        return self._keep_existing_image('about_photo')


class CaseAdminForm(ExistingImageFormMixin, forms.ModelForm):
    def clean_image(self):
        return self._keep_existing_image('image')


class FriendlySlugForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'slug' in self.fields:
            self.fields['slug'].required = False
            self.fields['slug'].label = 'Адрес страницы'
            self.fields['slug'].help_text = ('Можно оставить пустым: адрес создастся по названию. '
                                            'У опубликованной страницы лучше сохранять прежний адрес.')

    def clean_slug(self):
        value = self.cleaned_data.get('slug')
        if value:
            return value
        if self.instance.pk and self.instance.slug:
            return self.instance.slug
        limit = self._meta.model._meta.get_field('slug').max_length
        base = slugify(self.cleaned_data.get('title', ''), allow_unicode=True)[:limit] or 'page'
        value, index = base, 2
        while self._meta.model.objects.filter(slug=value).exclude(pk=self.instance.pk).exists():
            suffix = f'-{index}'
            value, index = base[:limit - len(suffix)] + suffix, index + 1
        return value


class PatientPageAdminForm(ExistingImageFormMixin, FriendlySlugForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'category' in self.fields:
            self.fields['category'].label = 'Раздел материалов'

    def clean_main_image(self):
        return self._keep_existing_image('main_image')


class DocumentAdminForm(FriendlySlugForm):
    purpose = forms.ChoiceField(label='Тип документа', choices=[
        ('other', 'Другой документ'), ('privacy', 'Политика конфиденциальности'),
        ('consent', 'Согласие на обработку персональных данных')],
        help_text='Для политики и согласия адрес настраивается автоматически.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purpose'].initial = self.instance.slug if self.instance.slug in ('privacy', 'consent') else 'other'

    def clean_slug(self):
        purpose = self.cleaned_data.get('purpose')
        return purpose if purpose in ('privacy', 'consent') else super().clean_slug()


class ImagePreviewAdminMixin:
    image_preview_width = 220

    def image_preview(self, obj, field_name):
        if not obj:
            return 'Изображение не загружено'
        image = getattr(obj, field_name, None)
        if not image:
            return 'Изображение не загружено'
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener">'
            '<img src="{0}" style="max-width:{1}px;max-height:160px;object-fit:contain;" />'
            '</a>',
            image.url,
            self.image_preview_width,
        )


class EditorialAdminMixin:
    save_on_top = True
    list_per_page = 25


class SingleSettingsAdmin(EditorialAdminMixin, admin.ModelAdmin):
    singleton_order = ('pk',)

    def render_change_form(self, request, context, *args, **kwargs):
        context['owner_section_tabs'] = True
        context['title'] = 'Главная страница' if self.model is HomePage else 'Контакты и настройки'
        context['subtitle'] = None
        return super().render_change_form(request, context, *args, **kwargs)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        selected = queryset.order_by(*self.singleton_order).first()
        return queryset.filter(pk=selected.pk) if selected else queryset.none()

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        selected = self.model.objects.order_by(*self.singleton_order).first()
        action = 'change' if selected else 'add'
        args = [selected.pk] if selected else []
        return redirect(reverse(f'admin:{self.opts.app_label}_{self.opts.model_name}_{action}', args=args))


@admin.register(SiteSettings)
class SiteSettingsAdmin(ImagePreviewAdminMixin, SingleSettingsAdmin):
    form = SiteSettingsAdminForm
    change_form_template = 'admin/core/sitesettings/change_form.html'
    list_display = ('doctor_name', 'phone', 'created_at')
    readonly_fields = ('logo_preview', 'backup_summary')
    fieldsets = (
        ('Имя и оформление', {
            'fields': ('doctor_name', 'short_name', 'specialty', 'logo_preview', 'logo', 'favicon', 'cta_text'),
            'description': 'Данные используются на всех страницах. Незаполненные контакты скрываются.'
        }),
        ('Контакты и клиника', {
            'fields': ('phone', 'contact_email', 'clinic_name', 'address', 'opening_hours', 'map_url')
        }),
        ('Интерактивная карта', {
            'fields': ('show_map', 'map_embed_url'),
            'description': 'Карта выводится в блоке клиники. Вставьте ссылку из src официального iframe, '
                           'а не весь HTML. Адрес и маршрут редактируются в группе контактов.'
        }),
        ('Социальные сети', {
            'fields': ('telegram_url', 'whatsapp_url', 'max_url', 'vk_url'), 'classes': ('collapse',),
            'description': 'WhatsApp, MAX и Telegram выводятся значками в самом низу сайта. '
                           'Вставьте HTTPS-ссылки на нужные чаты. Пока поле пустое, значок показан как неактивная заготовка.'
        }),
        ('Заявки и почта', {
            'fields': ('booking_enabled', 'notification_email', 'booking_title', 'booking_intro', 'booking_success_text'),
            'description': 'Для формы опубликуйте документы privacy и consent в разделе «Документы». '
                           'Внешнюю политику можно указать ниже. Заявки сохраняются независимо от доставки письма.'
        }),
        ('Расписание и бронирование', {
            'fields': ('schedule_enabled', 'schedule_title', 'schedule_intro'),
            'description': 'Окна создаются в разделе «Расписание приёма», по одному или сразу на неделю. '
                           'Демонстрационные окна явно помечены и не являются реальным приёмом.'
        }),
        ('Внутренние страницы', {
            'fields': ('patients_title', 'patients_intro', 'prices_intro', 'prices_note'), 'classes': ('collapse',)
        }),
        ('Поиск, подвал и документы', {
            'fields': ('site_description', 'footer_note', 'privacy_policy_url'), 'classes': ('collapse',)
        }),
        ('Резервные копии', {
            'fields': ('backup_summary',),
            'description': 'Полный архив включает SQLite, заявки, пользователей и загруженные файлы. '
                           'Копии хранятся приватно, не выдаются посетителям. Для отдельной внешней копии нужно подключить хранилище.'
        }),
    )

    def get_urls(self):
        return [path('<path:object_id>/test-email/', self.admin_site.admin_view(self.test_email_view),
                     name='core_sitesettings_test_email')] + super().get_urls()

    def change_view(self, request, object_id, form_url='', extra_context=None):
        site = self.get_object(request, object_id)
        if site and self.has_change_permission(request, site):
            from .notifications import uses_simple_mail
            simple_mail = uses_simple_mail()
            checks = [
                ('Приём заявок включён', site.booking_enabled),
                ('Почта получателя сохранена', bool(site.notification_email)),
            ]
            if not simple_mail:
                checks.extend([
                    ('Ключ Resend задан на сервере', bool(settings.RESEND_API_KEY)),
                    ('Адрес отправителя задан на сервере', bool(settings.DEFAULT_FROM_EMAIL)),
                ])
            checks.extend([
                ('Политика опубликована или указана внешняя ссылка', bool(site.privacy_policy_url)
                 or SitePage.objects.filter(slug='privacy', is_published=True).exists()),
                ('Согласие опубликовано (slug: consent)',
                 SitePage.objects.filter(slug='consent', is_published=True).exists()),
            ])
            extra_context = {**(extra_context or {}), 'booking_checks': checks,
                'simple_mail': simple_mail,
                'mail_test_ready': bool(site.notification_email and
                    (simple_mail or (settings.RESEND_API_KEY and settings.DEFAULT_FROM_EMAIL))),
                'saved_notification_email': site.notification_email,
                'test_email_url': reverse('admin:core_sitesettings_test_email', args=[site.pk])}
        return super().change_view(request, object_id, form_url, extra_context)

    @method_decorator(require_POST)
    def test_email_view(self, request, object_id):
        site = self.get_object(request, object_id)
        if not site:
            raise Http404
        if not self.has_change_permission(request, site):
            raise PermissionDenied
        from .notifications import send_test_notification, uses_simple_mail
        status, error = send_test_notification(site, site_url=request.build_absolute_uri('/'))
        if status == BookingRequest.Notification.SENT:
            text = f'Почтовый сервис принял тестовое письмо для {site.notification_email}. Проверьте входящие и спам.'
            if uses_simple_mail():
                text += ' При первом подключении откройте письмо от FormSubmit и нажмите кнопку подтверждения адреса.'
            self.message_user(request, text, level=messages.SUCCESS)
        else:
            self.message_user(request, error, level=messages.ERROR)
        return redirect(reverse('admin:core_sitesettings_change', args=[site.pk]))

    @admin.display(description='Текущий логотип')
    def logo_preview(self, obj):
        return self.image_preview(obj, 'logo')

    @admin.display(description='Последняя полная копия')
    def backup_summary(self, obj):
        archives = list((settings.DATA_DIR / 'backups').glob('site-full-*.zip'))
        if not archives:
            return 'Копия пока не создана. Запуск через run.ps1 или run_site включает ежедневное копирование SQLite.'
        latest = max(archives, key=lambda path: path.stat().st_mtime)
        created = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.get_current_timezone())
        return f'{created:%d.%m.%Y %H:%M} · {latest.stat().st_size / 1024 / 1024:.1f} МБ · архивов: {len(archives)}'


@admin.register(HomePage)
class HomePageAdmin(ImagePreviewAdminMixin, SingleSettingsAdmin):
    singleton_order = ('-created_at', '-pk')
    filter_horizontal = ('featured_patient_pages',)
    form = HomePageAdminForm
    list_display = (
        'id',
        'help_title',
        'about_title',
        'cases_title',
        'clinic_title',
        'prices_title',
        'reviews_title',
    )
    readonly_fields = ('hero_background_preview', 'about_photo_preview')
    fieldsets = (
        ('Первый экран', {
            'fields': ('hero_kicker', 'hero_title', 'hero_intro', 'hero_image', 'hero_image_alt',
                       'hero_image_position', 'use_default_artwork'),
            'description': 'Заголовок и изображение образуют первый экран. Фото можно заменить без изменения вёрстки.'
        }),
        ('Видимость разделов', {
            'fields': ('show_placeholders', 'show_directions', 'show_services', 'show_about', 'show_process',
                       'show_cases', 'show_clinic', 'show_prices', 'show_reviews', 'show_patient_materials', 'show_faq'),
            'description': 'Сохраните заготовки, пока наполняете сайт. Каждый раздел можно отдельно выключить.'
        }),
        ('С чем я могу помочь', {
            'fields': ('help_title', 'help_description')
        }),
        ('Каталог услуг', {
            'fields': ('services_title', 'services_description'),
            'description': 'Категории и услуги берутся из прайса. В направлениях можно выбрать варианты услуг и тип отображения.'
        }),
        ('Обо мне', {
            'fields': ('about_title', 'about_text', 'about_photo_preview', 'about_photo', 'about_photo_focus_y')
        }),
        ('Этапы обращения', {
            'fields': ('process_title', 'process_description', 'process_image'),
            'description': 'Сами этапы добавляются в отдельном разделе «Этапы обращения».'
        }),
        ('Кейсы', {
            'fields': ('cases_title', 'cases_description')
        }),
        ('Клиника', {
            'fields': ('clinic_title', 'clinic_description', 'clinic_directions'),
            'description': 'Адрес, название клиники и ссылка на маршрут — в общих настройках сайта.'
        }),
        ('Стоимость', {
            'fields': ('prices_title',)
        }),
        ('Отзывы', {
            'fields': ('reviews_title',)
        }),
        ('Материалы пациентам', {'fields': ('patient_materials_title', 'patient_materials_description', 'featured_patient_pages')}),
        ('Вопросы и ответы', {
            'fields': ('faq_title', 'faq_description'),
            'description': 'Вопросы добавляются в разделе «Вопросы и ответы».'
        }),
        ('Финальный блок', {'fields': ('final_title', 'final_text')}),
        ('Изображения прежней версии', {
            'fields': ('hero_background_preview', 'hero_background', 'clinic_photo'), 'classes': ('collapse',),
            'description': 'Архивные поля. Первый экран использует отдельное изображение; блок клиники — карту и описание.'
        }),
    )

    @admin.display(description='Текущий фон')
    def hero_background_preview(self, obj):
        return self.image_preview(obj, 'hero_background')

    @admin.display(description='Текущее фото врача')
    def about_photo_preview(self, obj):
        return self.image_preview(obj, 'about_photo')


@admin.register(Case)
class CaseAdmin(ImagePreviewAdminMixin, EditorialAdminMixin, admin.ModelAdmin):
    form = CaseAdminForm
    list_display = ('title', 'order', 'is_published')
    list_editable = ('order', 'is_published')
    search_fields = ('title', 'short_description')
    readonly_fields = ('case_image_preview',)
    fields = (
        'title',
        'short_description',
        'case_image_preview',
        'image',
        'detail_url',
        'order',
        'is_published',
    )

    @admin.display(description='Текущее изображение')
    def case_image_preview(self, obj):
        return self.image_preview(obj, 'image')


@admin.register(PriceItem)
class PriceItemAdmin(EditorialAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'category', 'price_text', 'unit_text', 'show_on_home', 'order', 'is_active')
    list_editable = ('price_text', 'unit_text', 'show_on_home', 'order', 'is_active')
    search_fields = ('title', 'description')
    list_filter = ('category', 'is_active', 'show_on_home')
    autocomplete_fields = ('category',)
    fields = ('category', 'title', 'price_text', 'unit_text', 'description', 'show_on_home', 'order', 'is_active')


@admin.register(Review)
class ReviewAdmin(EditorialAdminMixin, admin.ModelAdmin):
    list_display = ('patient_name', 'source', 'order', 'show_on_home', 'is_published')
    list_editable = ('order', 'show_on_home', 'is_published')
    search_fields = ('patient_name', 'text', 'source')
    list_filter = ('is_published', 'show_on_home')
    fields = ('patient_name', 'text', 'source', 'source_url', 'review_date', 'order', 'show_on_home', 'is_published')


@admin.register(PatientCategory)
class PatientCategoryAdmin(EditorialAdminMixin, admin.ModelAdmin):
    form = FriendlySlugForm
    list_display = ('title', 'order', 'is_published')
    list_editable = ('order', 'is_published')
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title',)
    fieldsets = (('Категория', {'fields': ('title', 'order', 'is_published')}),
                 ('Адрес страницы', {'fields': ('slug',), 'classes': ('collapse',)}))


class PatientPageSectionInlineForm(forms.ModelForm):
    class Meta:
        model = PatientPageSection
        fields = ('page', 'title', 'content', 'order')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.instance.content:
            self.fields['content'].required = False
            self.fields['content'].help_text = ('Пустой раздел из прежней версии. Его можно заполнить позже; '
                                               'пока он не выводится в статье и оглавлении.')


class PatientPageSectionInline(admin.StackedInline):
    model = PatientPageSection
    form = PatientPageSectionInlineForm
    extra = 0
    fields = ('title', 'content', 'order')
    verbose_name = 'раздел статьи'
    verbose_name_plural = 'Разделы статьи'


@admin.register(PatientPage)
class PatientPageAdmin(ImagePreviewAdminMixin, EditorialAdminMixin, admin.ModelAdmin):
    form = PatientPageAdminForm
    list_display = ('title', 'category', 'order', 'is_published')
    list_filter = ('category', 'is_published')
    list_editable = ('order', 'is_published')
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title', 'description', 'sections__title', 'sections__content')
    readonly_fields = ('main_image_preview',)
    inlines = (PatientPageSectionInline,)
    view_on_site = True
    fieldsets = (
        ('Основное', {
            'fields': ('category', 'title', 'description')
        }),
        ('Изображение', {
            'fields': ('main_image_preview', 'main_image', 'image_alt')
        }),
        ('Публикация', {
            'fields': ('order', 'is_published', 'source_url', 'author_name', 'reviewed_date')
        }),
        ('Адрес и поиск', {'fields': ('slug', 'seo_description'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Текущая основная картинка')
    def main_image_preview(self, obj):
        return self.image_preview(obj, 'main_image')


class OrderedContentAdmin(EditorialAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'order', 'is_published')
    list_editable = ('order', 'is_published')
    list_filter = ('is_published',)
    search_fields = ('title',)


@admin.register(Direction)
class DirectionAdmin(OrderedContentAdmin):
    autocomplete_fields = ('patient_page',)
    filter_horizontal = ('services',)
    fields = ('title', 'description', 'presentation', 'image', 'services', 'patient_page', 'url', 'order', 'is_published')


@admin.register(DoctorFact)
class DoctorFactAdmin(OrderedContentAdmin):
    fields = ('title', 'value', 'description', 'order', 'is_published')


@admin.register(FAQItem)
class FAQItemAdmin(EditorialAdminMixin, admin.ModelAdmin):
    list_display = ('question', 'order', 'is_published')
    list_editable = ('order', 'is_published')
    list_filter = ('is_published',)
    search_fields = ('question', 'answer')
    fields = ('question', 'answer', 'order', 'is_published')


@admin.register(ProcessStep)
class ProcessStepAdmin(OrderedContentAdmin):
    pass


@admin.register(Qualification)
class QualificationAdmin(OrderedContentAdmin):
    fields = ('year', 'title', 'organization', 'document', 'order', 'is_published')


class PriceItemInline(admin.TabularInline):
    model = PriceItem
    fields = ('title', 'price_text', 'unit_text', 'order', 'show_on_home', 'is_active')
    extra = 0
    show_change_link = True


@admin.register(PriceCategory)
class PriceCategoryAdmin(OrderedContentAdmin):
    list_display = ('title', 'unit_text', 'show_on_home', 'order', 'is_published')
    list_editable = ('show_on_home', 'order', 'is_published')
    inlines = (PriceItemInline,)


@admin.register(SitePage)
class SitePageAdmin(EditorialAdminMixin, admin.ModelAdmin):
    form = DocumentAdminForm
    list_display = ('title', 'slug', 'is_published')
    list_editable = ('is_published',)
    search_fields = ('title', 'body')
    prepopulated_fields = {'slug': ('title',)}
    view_on_site = True
    fieldsets = (('Документ', {'fields': ('purpose', 'title', 'body', 'is_published')}),
                 ('Адрес и поиск', {'fields': ('slug', 'seo_description'), 'classes': ('collapse',),
                    'description': 'Для политики и согласия адрес определяется типом документа. '
                                   'У остальных страниц можно оставить его пустым.'}))


@admin.register(BookingRequest)
class BookingRequestAdmin(EditorialAdminMixin, admin.ModelAdmin):
    actions = ('confirm_bookings', 'cancel_bookings', 'retry_notification')
    list_display = ('id', 'created_at', 'name', 'appointment_start', 'email', 'phone', 'status', 'is_demo', 'notification_status')
    list_filter = ('status', 'is_demo', 'notification_status', 'created_at')
    search_fields = ('name', 'phone', 'email')
    list_select_related = ('slot',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'name', 'email', 'phone', 'slot', 'appointment_start', 'appointment_duration',
                       'appointment_service', 'is_demo', 'status', 'consent', 'consent_document',
                       'notification_status', 'notification_error')
    fieldsets = (
        ('Пациент', {'fields': ('name', 'phone', 'email', 'note')}),
        ('Запись', {'fields': ('status', 'appointment_start', 'appointment_duration', 'appointment_service', 'is_demo')}),
        ('Уведомление', {'fields': ('notification_status', 'notification_error')}),
        ('Подробности заявки', {'fields': ('created_at', 'slot', 'consent', 'consent_document'), 'classes': ('collapse',)}),
    )
    change_form_template = 'admin/core/bookingrequest/change_form.html'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [path('<int:object_id>/decision/<str:decision>/', self.admin_site.admin_view(self.decision_view),
                     name='core_bookingrequest_decision')] + super().get_urls()

    @method_decorator(require_POST)
    def decision_view(self, request, object_id, decision):
        booking = self.get_object(request, str(object_id))
        if not booking:
            raise Http404
        if not self.has_change_permission(request, booking):
            raise PermissionDenied
        queryset = self.get_queryset(request).filter(pk=booking.pk)
        if decision == 'confirm':
            self.confirm_bookings(request, queryset)
        elif decision == 'cancel':
            self.cancel_bookings(request, queryset)
        else:
            raise Http404
        destination = request.POST.get('next', '')
        if destination.startswith(reverse('admin:index')) and url_has_allowed_host_and_scheme(
                destination, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(destination)
        return redirect(reverse('admin:core_bookingrequest_change', args=[booking.pk]))

    @admin.action(description='Подтвердить выбранные брони', permissions=['change'])
    def confirm_bookings(self, request, queryset):
        count = 0
        for booking in queryset.filter(slot__isnull=False, status__in=['new', 'contacted']):
            changed = BookingRequest.objects.filter(pk=booking.pk, status__in=['new', 'contacted']).update(status='confirmed')
            if changed:
                self.log_change(request, booking, 'Бронь подтверждена администратором.')
                count += 1
        self.message_user(request, f'Подтверждено броней: {count}. Время остаётся занятым.')

    @admin.action(description='Отменить и освободить время', permissions=['change'])
    def cancel_bookings(self, request, queryset):
        count = 0
        for booking in queryset.exclude(status='cancelled'):
            changed = BookingRequest.objects.filter(pk=booking.pk).exclude(status='cancelled').update(status='cancelled')
            if changed:
                self.log_change(request, booking, 'Бронь отменена, время освобождено.')
                count += 1
        self.message_user(request, f'Отменено заявок: {count}. Опубликованные будущие окна снова доступны, если не закрыты вручную.')

    @admin.action(description='Повторить почтовое уведомление', permissions=['change'])
    def retry_notification(self, request, queryset):
        from .notifications import notify_booking
        count = 0
        for booking in queryset.exclude(notification_status=BookingRequest.Notification.SENT)[:20]:
            notify_booking(booking, site_url=request.build_absolute_uri('/'))
            count += 1
        self.message_user(request, f'Обработано уведомлений: {count}. Результат указан в колонке «Уведомление».')


@admin.register(AppointmentSlot)
class AppointmentSlotAdmin(OwnerScheduleMixin, EditorialAdminMixin, admin.ModelAdmin):
    change_list_template = 'admin/core/appointmentslot/change_list.html'
    list_display = ('starts_at', 'service', 'duration_minutes', 'availability', 'reservation', 'is_demo', 'is_published', 'is_blocked')
    list_editable = ('is_published', 'is_blocked')
    list_filter = ('is_demo', 'is_published', 'is_blocked', 'starts_at')
    search_fields = ('service', 'note')
    date_hierarchy = 'starts_at'
    fields = ('service', 'starts_at', 'duration_minutes', 'is_demo', 'is_published', 'is_blocked', 'note')
    actions = ('close_slots', 'open_slots')

    def get_queryset(self, request):
        active = BookingRequest.objects.filter(slot_id=OuterRef('pk')).exclude(status='cancelled')
        return super().get_queryset(request).annotate(active_booking_id=Subquery(active.values('pk')[:1]))

    @admin.display(description='Состояние')
    def availability(self, obj):
        if obj.active_booking_id:
            return 'Занято'
        if not obj.is_published:
            return 'Не опубликовано'
        if obj.is_blocked:
            return 'Закрыто'
        return 'Прошедшее время' if obj.starts_at <= timezone.now() else 'Свободно'

    @admin.display(description='Бронь')
    def reservation(self, obj):
        if not obj.active_booking_id:
            return '—'
        return format_html('<a href="{}">Заявка №{}</a>',
            reverse('admin:core_bookingrequest_change', args=[obj.active_booking_id]), obj.active_booking_id)

    @admin.action(description='Закрыть для новых записей', permissions=['change'])
    def close_slots(self, request, queryset):
        count = queryset.update(is_blocked=True)
        self.message_user(request, f'Закрыто окон: {count}. Существующие брони сохранены.')

    @admin.action(description='Открыть для новых записей', permissions=['change'])
    def open_slots(self, request, queryset):
        count = queryset.update(is_blocked=False)
        self.message_user(request, f'Открыто окон: {count}. Занятые окна останутся недоступными.')

    def get_urls(self):
        return [path('generate/', self.admin_site.admin_view(self.generate_view),
                     name='core_appointmentslot_generate')] + super().get_urls()

    def generate_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        today = timezone.localdate()
        next_monday = today + timedelta(days=7 - today.weekday())
        form = SlotGenerationForm(request.POST if request.method == 'POST' else None,
                                  initial={'start_date': next_monday})
        if request.method == 'POST' and form.is_valid():
            count = skipped = 0
            try:
                with transaction.atomic():
                    for values in form.slot_values():
                        if AppointmentSlot.objects.filter(starts_at=values['starts_at']).exists():
                            skipped += 1
                            continue
                        slot = AppointmentSlot(**values)
                        slot.full_clean()
                        slot.save()
                        self.log_addition(request, slot, 'Создано через форму расписания на неделю.')
                        count += 1
            except ValidationError as exc:
                form.add_error(None, 'Не удалось создать расписание: ' + '; '.join(exc.messages))
            else:
                self.message_user(request, f'Создано окон: {count}. Уже существовавшие окна пропущены: {skipped}.')
                return redirect(self.calendar_url(monday(form.cleaned_data['start_date'])))
        return TemplateResponse(request, 'admin/core/appointmentslot/generate.html', {
            **self.admin_site.each_context(request), 'opts': self.model._meta,
            'title': 'Создать расписание на неделю', 'form': form, 'media': self.media + form.media,
        })


admin.site.site_header = 'Управление сайтом'
admin.site.site_title = 'Сайт врача'
admin.site.index_title = 'Контент и заявки'
