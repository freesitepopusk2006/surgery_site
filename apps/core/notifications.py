import json
import logging
from hashlib import sha256
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import BookingRequest, SiteSettings

logger = logging.getLogger(__name__)


def uses_simple_mail():
    return not bool(settings.RESEND_API_KEY)


def send_simple_notification(site, subject, text, site_url):
    """FormSubmit needs mailbox activation, but no account or API key."""
    payload = {'_subject': subject, 'message': text, '_captcha': 'false'}
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'SurgerySite/1.0'}
    if site_url:
        payload['_url'] = site_url
        origin = urlsplit(site_url)
        headers['Origin'] = f'{origin.scheme}://{origin.netloc}'
        headers['Referer'] = site_url
    request = Request(f'https://formsubmit.co/ajax/{quote(site.notification_email, safe="@")}',
                      data=json.dumps(payload).encode('utf-8'), method='POST', headers=headers)
    try:
        with urlopen(request, timeout=6) as response:
            if not 200 <= response.status < 300:
                raise URLError('Unexpected status')
            result = json.loads(response.read(16384))
            if not isinstance(result, dict) or result.get('success') not in (True, 'true'):
                raise ValueError('Submission not accepted')
        return BookingRequest.Notification.SENT, ''
    except (HTTPError, URLError, OSError, ValueError):
        logger.warning('Simple email service did not confirm notification')
        return (BookingRequest.Notification.FAILED,
                'FormSubmit не принял уведомление. Проверьте соединение и повторите. '
                'Для начала работы подтвердите адрес в письме от FormSubmit; проверьте также спам.')


def send_notification(site, subject, text, message_key, *, site_url=''):
    """Return a safe status; provider responses and credentials stay off admin pages."""
    if not site or not site.notification_email:
        return BookingRequest.Notification.UNCONFIGURED, 'Укажите почту получателя в настройках сайта.'
    if uses_simple_mail():
        return send_simple_notification(site, subject, text, site_url)
    if not settings.DEFAULT_FROM_EMAIL:
        return (BookingRequest.Notification.UNCONFIGURED,
                'Укажите почту получателя, RESEND_API_KEY и DEFAULT_FROM_EMAIL.')
    payload = json.dumps({
        'from': settings.DEFAULT_FROM_EMAIL,
        'to': [site.notification_email],
        'subject': subject,
        'text': text,
    }).encode('utf-8')
    # A changed recipient/sender is a new delivery, while retries remain idempotent.
    route = sha256(f'{settings.DEFAULT_FROM_EMAIL}\n{site.notification_email}'.encode()).hexdigest()[:24]
    request = Request('https://api.resend.com/emails', data=payload, method='POST', headers={
        'Authorization': f'Bearer {settings.RESEND_API_KEY}',
        'Content-Type': 'application/json',
        'User-Agent': 'SurgerySite/1.0',
        'Idempotency-Key': f'{message_key}/{route}',
    })
    try:
        with urlopen(request, timeout=6) as response:
            if not 200 <= response.status < 300:
                raise URLError('Unexpected status')
            result = json.loads(response.read(16384))
            if not isinstance(result, dict) or not isinstance(result.get('id'), str) or not result['id']:
                raise ValueError('Missing message ID')
        return BookingRequest.Notification.SENT, ''
    except HTTPError as exc:
        errors = {
            401: 'Ключ Resend отклонён. Проверьте RESEND_API_KEY на сервере.',
            403: 'Resend запретил отправку. Проверьте отправителя, подтверждение домена и права ключа. '
                 'С onboarding@resend.dev можно отправлять только на почту владельца аккаунта Resend.',
            429: 'Достигнут лимит Resend. Повторите отправку позже.',
        }
        error = errors.get(exc.code, 'Почтовый сервис отклонил отправку. Проверьте его настройки и повторите.')
        logger.warning('Email service rejected notification (HTTP %s)', exc.code)
        return BookingRequest.Notification.FAILED, error
    except (URLError, OSError, ValueError):
        logger.warning('Email service did not confirm notification')
        return (BookingRequest.Notification.FAILED,
                'Почтовый сервис не подтвердил отправку. Проверьте настройки и повторите.')


def send_test_notification(site, *, site_url=''):
    return send_notification(site, 'Проверка уведомлений сайта',
        'Это тестовое письмо из админки сайта.\n'
        'Уведомления о новых заявках будут приходить на этот адрес.\n'
        'Тест не создаёт заявку и не содержит данных пациентов.', f'test/{uuid4()}', site_url=site_url)


def notify_booking(booking, *, site_url=''):
    site = SiteSettings.objects.order_by('pk').first()
    admin_path = reverse('admin:core_bookingrequest_change', args=[booking.pk])
    admin_url = urljoin(site_url, admin_path) if site_url else admin_path
    subject = f'Новая заявка на приём #{booking.pk}'
    text = (f'На сайте сохранена новая заявка #{booking.pk}.\n'
            f'Посмотреть имя и телефон в админке: {admin_url}\n'
            'Для просмотра войдите в учётную запись администратора.')
    if booking.slot_id:
        start = timezone.localtime(booking.appointment_start)
        subject = f'{"Демо · " if booking.is_demo else ""}Бронь №{booking.pk} · {start:%d.%m, %H:%M}'
        text = (f'БРОНЬ №{booking.pk} — ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ\n'
            + ('Демонстрационная запись. Реального приёма не будет.\n' if booking.is_demo else '')
            + f'\nУслуга: {booking.appointment_service}\nДата: {start:%d.%m.%Y}\n'
              f'Время: {start:%H:%M} (Москва, UTC+3)\nДлительность: {booking.appointment_duration} минут\n'
              f'\nФИО: {booking.name}\nТелефон: {booking.phone}\nПочта: {booking.email}\n'
              f'\nПодтвердить или отменить после входа в админку:\n{admin_url}\n'
              '\nДо решения администратора это время недоступно для других записей.')
    booking.notification_status, booking.notification_error = send_notification(site,
        subject, text, f'booking/{booking.pk}', site_url=site_url)
    booking.save(update_fields=['notification_status', 'notification_error'])
    return booking.notification_status
