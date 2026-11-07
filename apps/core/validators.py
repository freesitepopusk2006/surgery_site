from urllib.parse import urlsplit

from django.core.exceptions import ValidationError


def validate_map_embed_url(value):
    """Accept official map-widget URLs, never arbitrary iframe HTML or hosts."""
    if not value:
        return
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower()
        valid_host_path = (
            host in {'yandex.ru', 'yandex.com'} and parsed.path.startswith('/map-widget/v1/')
        ) or (
            host in {'www.google.com', 'maps.google.com'} and parsed.path.startswith('/maps/embed')
        )
        valid = (parsed.scheme == 'https' and not parsed.username and not parsed.password
                 and parsed.port in {None, 443} and valid_host_path)
    except ValueError:
        valid = False
    if not valid:
        raise ValidationError('Укажите HTTPS-ссылку встраивания Яндекс Карт или Google Maps. '
                              'Нужна ссылка из src iframe, без HTML-кода.')
