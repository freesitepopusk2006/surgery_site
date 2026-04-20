from django.contrib import admin
from .models import SiteSettings, HomePage, Case, PriceItem, Review


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ('doctor_name', 'phone', 'created_at')
    fieldsets = (
        ('Шапка сайта', {
            'fields': ('logo', 'phone', 'cta_text')
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


@admin.register(HomePage)
class HomePageAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'help_title',
        'about_title',
        'cases_title',
        'clinic_title',
        'prices_title',
        'reviews_title',
    )
    fieldsets = (
        ('Фон', {
            'fields': ('hero_background',)
        }),
        ('С чем я могу помочь', {
            'fields': ('help_title', 'help_description')
        }),
        ('Обо мне', {
            'fields': ('about_title', 'about_text', 'about_photo')
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


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'is_published')
    list_editable = ('order', 'is_published')
    search_fields = ('title', 'short_description')


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
