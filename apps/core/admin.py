from django.contrib import admin
from django import forms
from django.utils.html import format_html
from .models import SiteSettings, HomePage, Case, PriceItem, Review


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


@admin.register(SiteSettings)
class SiteSettingsAdmin(ImagePreviewAdminMixin, admin.ModelAdmin):
    form = SiteSettingsAdminForm
    list_display = ('doctor_name', 'phone', 'created_at')
    readonly_fields = ('logo_preview',)
    fieldsets = (
        ('Шапка сайта', {
            'fields': ('logo_preview', 'logo', 'phone', 'cta_text')
        }),
        ('Футер', {
            'fields': ('doctor_name', 'address')
        }),
        ('Социальные сети', {
            'fields': ('telegram_url', 'whatsapp_url', 'max_url')
        }),
        ('Политика', {
            'fields': ('privacy_policy_url',)
        }),
    )

    @admin.display(description='Текущий логотип')
    def logo_preview(self, obj):
        return self.image_preview(obj, 'logo')


@admin.register(HomePage)
class HomePageAdmin(ImagePreviewAdminMixin, admin.ModelAdmin):
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
        ('Фон', {
            'fields': ('hero_background_preview', 'hero_background')
        }),
        ('С чем я могу помочь', {
            'fields': ('help_title', 'help_description')
        }),
        ('Обо мне', {
            'fields': ('about_title', 'about_text', 'about_photo_preview', 'about_photo')
        }),
        ('Кейсы', {
            'fields': ('cases_title', 'cases_description')
        }),
        ('Клиника', {
            'fields': ('clinic_title', 'clinic_description', 'clinic_map_embed')
        }),
        ('Стоимость', {
            'fields': ('prices_title',)
        }),
        ('Отзывы', {
            'fields': ('reviews_title',)
        }),
    )

    @admin.display(description='Текущий фон')
    def hero_background_preview(self, obj):
        return self.image_preview(obj, 'hero_background')

    @admin.display(description='Текущее фото врача')
    def about_photo_preview(self, obj):
        return self.image_preview(obj, 'about_photo')


@admin.register(Case)
class CaseAdmin(ImagePreviewAdminMixin, admin.ModelAdmin):
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
class PriceItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'price_text', 'order', 'is_active')
    list_editable = ('price_text', 'order', 'is_active')
    search_fields = ('title', 'description')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('patient_name', 'source', 'order', 'show_on_home', 'is_published')
    list_editable = ('order', 'show_on_home', 'is_published')
    search_fields = ('patient_name', 'text', 'source')
