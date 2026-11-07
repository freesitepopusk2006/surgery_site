from django.db import models
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator
from django.urls import reverse
from django.core.exceptions import ValidationError
from .validators import validate_map_embed_url


class SiteSettings(models.Model):
    contact_email = models.EmailField('Публичная почта центра', blank=True,
        help_text='Показывается посетителям. Не меняет получателя заявок.')
    map_embed_url = models.URLField('Ссылка встраивания интерактивной карты', max_length=1500, blank=True,
        validators=[validate_map_embed_url],
        help_text='Ссылка из src iframe Яндекс Карт или Google Maps. Маршрут укажите в отдельном поле ниже.')
    show_map = models.BooleanField('Показывать интерактивную карту', default=True)

    @property
    def safe_map_embed_url(self):
        if not self.show_map:
            return ''
        try:
            validate_map_embed_url(self.map_embed_url)
        except ValidationError:
            return ''
        return self.map_embed_url

    specialty = models.CharField('Специализация', max_length=180, blank=True)
    short_name = models.CharField('Имя в шапке', max_length=120, blank=True,
                                  help_text='Короткое имя или название. Полное ФИО укажите ниже.')
    favicon = models.ImageField('Иконка вкладки', upload_to='branding/', blank=True)
    site_description = models.TextField('Описание сайта для поиска', blank=True)
    footer_note = models.TextField('Подпись в подвале', blank=True)
    clinic_name = models.CharField('Название клиники', max_length=255, blank=True)
    opening_hours = models.CharField('Часы приёма / связи', max_length=255, blank=True)
    map_url = models.URLField('Ссылка на маршрут', blank=True,
                             help_text='Обычная ссылка на Яндекс Карты или другую карту, без HTML.')
    booking_enabled = models.BooleanField('Принимать заявки на сайте', default=True)
    notification_email = models.EmailField('Почта для уведомлений о заявках', blank=True,
        help_text='Адрес получателя. Ключ почтового сервиса задаётся в окружении сервера.')
    booking_title = models.CharField('Заголовок формы', max_length=180, default='Запись на приём')
    booking_intro = models.TextField('Пояснение к форме', blank=True)
    booking_success_text = models.TextField('Подтверждение заявки', blank=True,
        help_text='Показывается после сохранения заявки. Не указывайте неподтверждённые сроки ответа.')
    patients_title = models.CharField('Заголовок раздела пациентам', max_length=180, default='Пациентам')
    patients_intro = models.TextField('Введение в раздел пациентам', blank=True)
    prices_intro = models.TextField('Введение в прайс', blank=True)
    prices_note = models.TextField('Условия и примечание к прайсу', blank=True)
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

    max_url = models.URLField(
        blank=True,
        verbose_name='Ссылка на Max'
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
    about_photo_focus_y = models.PositiveSmallIntegerField('Положение портрета по вертикали, %', default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='0 — верх кадра, 50 — центр, 100 — низ. Позволяет настроить кадр без изменения исходного фото.')
    show_placeholders = models.BooleanField('Показывать заготовки пустых разделов', default=True,
        help_text='Сохраняет полную композицию до наполнения. Заготовки не содержат вымышленных данных. '
                  'После заполнения можно выключить: незаполненные разделы будут скрыты.')
    show_services = models.BooleanField('Каталог услуг на главной', default=True)
    services_title = models.CharField('Заголовок каталога услуг', max_length=255, default='Услуги и лечение')
    services_description = models.TextField('Введение в каталог услуг', blank=True)
    show_patient_materials = models.BooleanField('Материалы пациентам на главной', default=True)
    patient_materials_title = models.CharField('Заголовок материалов на главной', max_length=255,
                                               default='Полезно знать до приёма')
    patient_materials_description = models.TextField('Введение к материалам', blank=True)
    featured_patient_pages = models.ManyToManyField('PatientPage', blank=True, related_name='featured_on',
        verbose_name='Материалы на главной', help_text='Выберите до 6 статей. Если выбор пустой, выводятся первые 3 опубликованные.')
    show_faq = models.BooleanField('Ответы на вопросы', default=True)
    faq_title = models.CharField('Заголовок вопросов', max_length=255, default='Ответы на ваши вопросы')
    faq_description = models.TextField('Введение к вопросам', blank=True)
    hero_kicker = models.CharField('Подпись над заголовком', max_length=120, blank=True)
    hero_title = models.TextField('Заголовок первого экрана', default='Зрение.\nВ центре внимания.',
        help_text='Переносы строк сохраняются на большом экране. Текст можно полностью заменить.')
    hero_intro = models.TextField('Текст первого экрана', blank=True)
    hero_image = models.ImageField('Изображение первого экрана', upload_to='homepage/', blank=True,
        help_text='Портрет или оптический образ. Желательно от 1400 px, вертикальный кадр 4:5.')
    hero_image_alt = models.CharField('Описание изображения', max_length=255, blank=True)
    hero_image_position = models.CharField('Положение кадра', max_length=12, default='center',
        choices=[('center', 'По центру'), ('top', 'Сверху'), ('bottom', 'Снизу')])
    use_default_artwork = models.BooleanField('Показывать оптические иллюстрации оформления', default=True,
        help_text='Используются, когда свои изображения первого экрана и подхода не загружены.')
    process_title = models.CharField('Заголовок этапов обращения', max_length=255,
        default='От первого вопроса до понятного плана.')
    process_description = models.TextField('Введение к этапам', blank=True)
    process_image = models.ImageField('Изображение этапов', upload_to='homepage/', blank=True)
    clinic_photo = models.ImageField('Фото клиники', upload_to='clinic/', blank=True)
    clinic_directions = models.TextField('Как добраться', blank=True)
    final_title = models.CharField('Заголовок финального блока', max_length=255,
                                  default='Начнём с консультации.')
    final_text = models.TextField('Текст финального блока', blank=True)
    show_directions = models.BooleanField('Направления', default=True)
    show_about = models.BooleanField('О враче', default=True)
    show_process = models.BooleanField('Этапы обращения', default=True)
    show_cases = models.BooleanField('Кейсы', default=False)
    show_clinic = models.BooleanField('Клиника', default=True)
    show_prices = models.BooleanField('Выбранные цены', default=True)
    show_reviews = models.BooleanField('Отзывы', default=True)
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
    @property
    def unit_label(self):
        return self.unit_text or (self.category.unit_text if self.category_id else '')

    category = models.ForeignKey('PriceCategory', on_delete=models.SET_NULL, blank=True, null=True,
                                 related_name='items', verbose_name='Категория')
    unit_text = models.CharField('Единица / условия расчёта', max_length=180, blank=True,
        help_text='Например: за один глаз. Если пусто — используется подпись категории.')
    show_on_home = models.BooleanField('Показать на главной', default=False)
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
    source_url = models.URLField('Ссылка на оригинал', blank=True)
    review_date = models.DateField('Дата отзыва', blank=True, null=True)
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


class PatientCategory(models.Model):
    title = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='Название раздела'
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        allow_unicode=True,
        verbose_name='URL раздела'
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
        verbose_name = 'Раздел для пациентов'
        verbose_name_plural = 'Разделы для пациентов'

    def __str__(self):
        return self.title


class PatientPage(models.Model):
    seo_description = models.CharField('Описание для поиска', max_length=300, blank=True)
    image_alt = models.CharField('Описание иллюстрации', max_length=255, blank=True)
    author_name = models.CharField('Автор / проверивший врач', max_length=255, blank=True)
    reviewed_date = models.DateField('Дата проверки материала', blank=True, null=True)

    def get_absolute_url(self):
        return reverse('core:patient_page_detail', args=[self.slug])
    category = models.ForeignKey(
        PatientCategory,
        on_delete=models.CASCADE,
        related_name='pages',
        verbose_name='Раздел'
    )
    title = models.CharField(
        max_length=255,
        verbose_name='Заголовок'
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        allow_unicode=True,
        verbose_name='URL страницы'
    )
    description = models.TextField(
        blank=True,
        verbose_name='Описание'
    )
    main_image = models.ImageField(
        upload_to='patients/',
        blank=True,
        null=True,
        verbose_name='Основная картинка'
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок'
    )
    is_published = models.BooleanField(
        default=True,
        verbose_name='Опубликовано'
    )
    source_url = models.URLField(
        blank=True,
        verbose_name='Источник'
    )

    class Meta:
        ordering = ['category__order', 'order', 'id']
        verbose_name = 'Страница для пациентов'
        verbose_name_plural = 'Страницы для пациентов'

    def __str__(self):
        return self.title


class PatientPageSection(models.Model):
    page = models.ForeignKey(
        PatientPage,
        on_delete=models.CASCADE,
        related_name='sections',
        verbose_name='Страница'
    )
    title = models.CharField(
        max_length=255,
        verbose_name='Название части'
    )
    content = models.TextField(
        verbose_name='Контент'
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок'
    )

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Часть страницы для пациентов'
        verbose_name_plural = 'Части страниц для пациентов'

    def __str__(self):
        return self.title


class OrderedPublishedModel(models.Model):
    order = models.PositiveIntegerField('Порядок', default=0)
    is_published = models.BooleanField('Опубликовано', default=True)

    class Meta:
        abstract = True
        ordering = ['order', 'id']


class Direction(OrderedPublishedModel):
    presentation = models.CharField('Отображение', max_length=16, default='expandable', choices=[
        ('row', 'Лаконичная строка'), ('expandable', 'Раскрытие вариантов услуг'), ('card', 'Карточка с изображением')])
    image = models.ImageField('Изображение направления', upload_to='directions/', blank=True)
    services = models.ManyToManyField(PriceItem, blank=True, related_name='directions',
        verbose_name='Варианты услуг', help_text='Услуги берутся из прайса. Неактивные позиции и скрытые категории не выводятся.')
    title = models.CharField('Название', max_length=255)
    description = models.TextField('Краткое описание', blank=True)
    patient_page = models.ForeignKey(PatientPage, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Связанная статья', help_text='Ссылка появится, только если статья и её категория опубликованы.')
    url = models.URLField('Внешняя ссылка', blank=True,
        help_text='Необязательно. Связанная статья имеет приоритет.')

    class Meta(OrderedPublishedModel.Meta):
        verbose_name = 'Направление'
        verbose_name_plural = 'Направления помощи'

    def __str__(self):
        return self.title

    @property
    def link(self):
        if self.patient_page_id:
            if self.patient_page.is_published and self.patient_page.category.is_published:
                return self.patient_page.get_absolute_url()
            return ''
        return self.url


class ProcessStep(OrderedPublishedModel):
    title = models.CharField('Название этапа', max_length=180)
    description = models.TextField('Описание', blank=True)

    class Meta(OrderedPublishedModel.Meta):
        verbose_name = 'Этап обращения'
        verbose_name_plural = 'Этапы обращения'

    def __str__(self):
        return self.title


class DoctorFact(OrderedPublishedModel):
    title = models.CharField('Подпись', max_length=120)
    value = models.CharField('Значение / основной текст', max_length=180)
    description = models.TextField('Пояснение', blank=True)

    class Meta(OrderedPublishedModel.Meta):
        verbose_name = 'Факт о враче'
        verbose_name_plural = 'Факты о враче'

    def __str__(self):
        return self.title


class FAQItem(OrderedPublishedModel):
    question = models.CharField('Вопрос', max_length=255)
    answer = models.TextField('Ответ', help_text='Абзацы разделяйте пустой строкой, списки начинайте с «- ».')

    class Meta(OrderedPublishedModel.Meta):
        verbose_name = 'Вопрос и ответ'
        verbose_name_plural = 'Вопросы и ответы'

    def __str__(self):
        return self.question


class Qualification(OrderedPublishedModel):
    year = models.CharField('Год / период', max_length=60, blank=True)
    title = models.CharField('Образование / квалификация', max_length=255)
    organization = models.CharField('Организация', max_length=255, blank=True)
    document = models.FileField('Документ', upload_to='qualifications/', blank=True,
        validators=[FileExtensionValidator(['pdf', 'png', 'jpg', 'jpeg', 'webp'])],
        help_text='Опубликованный файл доступен посетителям. PDF, JPG, PNG или WebP.')

    class Meta(OrderedPublishedModel.Meta):
        verbose_name = 'Образование / квалификация'
        verbose_name_plural = 'Образование и квалификация'

    def __str__(self):
        return self.title


class PriceCategory(OrderedPublishedModel):
    show_on_home = models.BooleanField('Показать в каталоге главной', default=True)
    title = models.CharField('Название категории', max_length=255)
    unit_text = models.CharField('Общая единица расчёта', max_length=180, blank=True,
        help_text='Например: цена за оба глаза. Услуга может иметь собственную подпись.')

    class Meta(OrderedPublishedModel.Meta):
        verbose_name = 'Категория прайса'
        verbose_name_plural = 'Категории прайса'

    def __str__(self):
        return self.title


class SitePage(models.Model):
    title = models.CharField('Заголовок', max_length=255)
    slug = models.SlugField('Адрес', max_length=180, unique=True, allow_unicode=True,
        help_text='Для политики используйте privacy, для согласия — consent.')
    body = models.TextField('Текст', help_text='Абзацы разделяйте пустой строкой; списки начинайте с «- ».')
    seo_description = models.CharField('Описание для поиска', max_length=300, blank=True)
    is_published = models.BooleanField('Опубликовано', default=False)

    class Meta:
        verbose_name = 'Документ / страница'
        verbose_name_plural = 'Документы и служебные страницы'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('core:site_page', args=[self.slug])


class BookingRequest(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новая'
        CONTACTED = 'contacted', 'Связались'
        CLOSED = 'closed', 'Закрыта'

    class Notification(models.TextChoices):
        PENDING = 'pending', 'Ожидает отправки'
        SENT = 'sent', 'Доставлено почтовому сервису'
        FAILED = 'failed', 'Ошибка отправки'
        UNCONFIGURED = 'unconfigured', 'Почта не настроена'

    name = models.CharField('Имя', max_length=120)
    phone = models.CharField('Телефон', max_length=30)
    consent = models.BooleanField('Согласие на обработку данных')
    consent_document = models.CharField('Документ согласия при отправке', max_length=500, blank=True)
    created_at = models.DateTimeField('Поступила', auto_now_add=True, db_index=True)
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.NEW)
    notification_status = models.CharField('Уведомление', max_length=20, choices=Notification.choices,
                                          default=Notification.PENDING)
    notification_error = models.CharField('Причина ошибки уведомления', max_length=255, blank=True)
    note = models.TextField('Заметка администратора', blank=True)
    throttle_key = models.CharField(max_length=64, blank=True, db_index=True, editable=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Заявка на приём'
        verbose_name_plural = 'Заявки на приём'

    def __str__(self):
        return f'Заявка #{self.pk} · {self.name}'
