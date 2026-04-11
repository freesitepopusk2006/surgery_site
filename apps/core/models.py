from django.db import models


class SiteSettings(models.Model):
    logo = models.ImageField(
        upload_to='branding/',
        blank=True,
        null=True,
        verbose_name='Логотип / иконка'
    )
    phone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Телефон'
    )
    cta_text = models.CharField(
        max_length=100,
        default='Запись на приём',
        verbose_name='Текст кнопки записи'
    )

    doctor_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Имя и фамилия'
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Адрес'
    )

    telegram_url = models.URLField(
        blank=True,
        verbose_name='Ссылка на Telegram'
    )
    vk_url = models.URLField(
        blank=True,
        verbose_name='Ссылка на VK'
    )
    whatsapp_url = models.URLField(
        blank=True,
        verbose_name='Ссылка на WhatsApp'
    )

    privacy_policy_url = models.URLField(
        blank=True,
        verbose_name='Ссылка на политику конфиденциальности'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Настройки сайта'
        verbose_name_plural = 'Настройки сайта'

    def __str__(self):
        return self.doctor_name or 'Настройки сайта'


class HomePage(models.Model):
    hero_background = models.ImageField(
        upload_to='homepage/',
        blank=True,
        null=True,
        verbose_name='Фоновое изображение страницы'
    )

    help_title = models.CharField(
        max_length=255,
        default='С чем я могу помочь',
        verbose_name='Заголовок блока помощи'
    )
    help_description = models.TextField(
        blank=True,
        verbose_name='Описание блока помощи'
    )

    about_title = models.CharField(
        max_length=255,
        default='Профессиональный подход и современная хирургия',
        verbose_name='Заголовок блока "Обо мне"'
    )
    about_text = models.TextField(
        blank=True,
        verbose_name='Текст блока "Обо мне"'
    )
    about_photo = models.ImageField(
        upload_to='about/',
        blank=True,
        null=True,
        verbose_name='Фото врача'
    )

    cases_title = models.CharField(
        max_length=255,
        default='Примеры работ',
        verbose_name='Заголовок блока кейсов'
    )
    cases_description = models.TextField(
        blank=True,
        verbose_name='Описание блока кейсов'
    )

    clinic_title = models.CharField(
        max_length=255,
        default='Где проходит приём',
        verbose_name='Заголовок блока клиники'
    )
    clinic_description = models.TextField(
        blank=True,
        verbose_name='Описание блока клиники'
    )
    clinic_map_embed = models.TextField(
        blank=True,
        verbose_name='HTML / iframe карты'
    )

    prices_title = models.CharField(
        max_length=255,
        default='Услуги и цены',
        verbose_name='Заголовок блока цен'
    )

    reviews_title = models.CharField(
        max_length=255,
        default='Что говорят пациенты',
        verbose_name='Заголовок блока отзывов'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Главная страница'
        verbose_name_plural = 'Главная страница'

    def __str__(self):
        return f'Главная страница #{self.pk}'


class Case(models.Model):
    title = models.CharField(
        max_length=255,
        verbose_name='Название кейса'
    )
    short_description = models.TextField(
        blank=True,
        verbose_name='Краткое описание'
    )
    image = models.ImageField(
        upload_to='cases/',
        blank=True,
        null=True,
        verbose_name='Изображение кейса'
    )
    detail_url = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Ссылка "Читать подробнее"'
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок'
    )
    is_published = models.BooleanField(
        default=True,
        verbose_name='Опубликовано'
    )

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Кейс'
        verbose_name_plural = 'Кейсы'

    def __str__(self):
        return self.title


class PriceItem(models.Model):
    title = models.CharField(
        max_length=255,
        verbose_name='Название услуги'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Описание'
    )
    price_text = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Цена / подпись цены'
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активно'
    )

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Услуга / цена'
        verbose_name_plural = 'Услуги / цены'

    def __str__(self):
        return self.title


class Review(models.Model):
    patient_name = models.CharField(
        max_length=255,
        verbose_name='Имя пациента'
    )
    text = models.TextField(
        verbose_name='Текст отзыва'
    )
    source = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Источник'
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок'
    )
    show_on_home = models.BooleanField(
        default=True,
        verbose_name='Показывать на главной'
    )
    is_published = models.BooleanField(
        default=True,
        verbose_name='Опубликовано'
    )

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'

    def __str__(self):
        return self.patient_name
