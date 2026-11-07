from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.shortcuts import redirect
from django.urls import reverse
from .models import (
    SiteSettings,
    HomePage,
    Case,
    PriceItem,
    Review,
    PatientCategory,
    PatientPage,
    PatientPageSection,
    Direction, ProcessStep, Qualification, PriceCategory, SitePage, BookingRequest, DoctorFact, FAQItem,
)


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


class PatientPageAdminForm(ExistingImageFormMixin, forms.ModelForm):
    def clean_main_image(self):
        return self._keep_existing_image('main_image')


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

    class Media:
        css = {'all': ('core/css/admin.css',)}
        js = ('core/js/admin.js',)


class SingleSettingsAdmin(EditorialAdminMixin, admin.ModelAdmin):
    singleton_order = ('pk',)

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
    list_display = ('doctor_name', 'phone', 'created_at')
    readonly_fields = ('logo_preview',)
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
            'fields': ('telegram_url', 'whatsapp_url', 'max_url', 'vk_url'), 'classes': ('collapse',)
        }),
        ('Заявки и почта', {
            'fields': ('booking_enabled', 'notification_email', 'booking_title', 'booking_intro', 'booking_success_text'),
            'description': 'Для формы опубликуйте документы privacy и consent в разделе «Документы». '
                           'Внешнюю политику можно указать ниже. Заявки сохраняются независимо от доставки письма.'
        }),
        ('Внутренние страницы', {
            'fields': ('patients_title', 'patients_intro', 'prices_intro', 'prices_note'), 'classes': ('collapse',)
        }),
        ('Поиск, подвал и документы', {
            'fields': ('site_description', 'footer_note', 'privacy_policy_url'), 'classes': ('collapse',)
        }),
    )

    @admin.display(description='Текущий логотип')
    def logo_preview(self, obj):
        return self.image_preview(obj, 'logo')


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
            'fields': ('about_title', 'about_text', 'about_photo_preview', 'about_photo')
        }),
        ('Этапы обращения', {
            'fields': ('process_title', 'process_description', 'process_image'),
            'description': 'Сами этапы добавляются в отдельном разделе «Этапы обращения».'
        }),
        ('Кейсы', {
            'fields': ('cases_title', 'cases_description')
        }),
        ('Клиника', {
            'fields': ('clinic_title', 'clinic_description', 'clinic_photo', 'clinic_directions'),
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
        ('Изображение прежней версии', {
            'fields': ('hero_background_preview', 'hero_background'), 'classes': ('collapse',),
            'description': 'Архивное поле. Для нового дизайна используйте изображение первого экрана выше.'
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
    list_display = ('title', 'order', 'is_published')
    list_editable = ('order', 'is_published')
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title',)


class PatientPageSectionInline(admin.StackedInline):
    model = PatientPageSection
    extra = 0
    fields = ('title', 'content', 'order')


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
            'fields': ('category', 'title', 'slug', 'description')
        }),
        ('Изображение', {
            'fields': ('main_image_preview', 'main_image', 'image_alt')
        }),
        ('Публикация', {
            'fields': ('order', 'is_published', 'source_url', 'author_name', 'reviewed_date')
        }),
        ('Поиск', {'fields': ('seo_description',), 'classes': ('collapse',)}),
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
    list_display = ('title', 'slug', 'is_published')
    list_editable = ('is_published',)
    search_fields = ('title', 'body')
    prepopulated_fields = {'slug': ('title',)}
    view_on_site = True
    fields = ('title', 'slug', 'body', 'seo_description', 'is_published')


@admin.register(BookingRequest)
class BookingRequestAdmin(EditorialAdminMixin, admin.ModelAdmin):
    actions = ('retry_notification',)
    list_display = ('id', 'created_at', 'name', 'phone', 'status', 'notification_status')
    list_editable = ('status',)
    list_filter = ('status', 'notification_status', 'created_at')
    search_fields = ('name', 'phone')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'name', 'phone', 'consent', 'consent_document',
                       'notification_status', 'notification_error')
    fields = ('created_at', 'name', 'phone', 'consent', 'consent_document', 'status', 'note',
              'notification_status', 'notification_error')

    def has_add_permission(self, request):
        return False

    @admin.action(description='Повторить почтовое уведомление', permissions=['change'])
    def retry_notification(self, request, queryset):
        from .notifications import notify_booking
        count = 0
        for booking in queryset.exclude(notification_status=BookingRequest.Notification.SENT)[:20]:
            notify_booking(booking)
            count += 1
        self.message_user(request, f'Обработано уведомлений: {count}. Результат указан в колонке «Уведомление».')


admin.site.site_header = 'Управление сайтом'
admin.site.site_title = 'Сайт врача'
admin.site.index_title = 'Контент и заявки'
