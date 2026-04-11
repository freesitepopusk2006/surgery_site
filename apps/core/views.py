from django.shortcuts import render


def home_view(request):
    context = {
        'page_title': 'Главная',
        'nav_links': [
            {'label': 'Обо мне', 'href': '#about'},
            {'label': 'Отзывы', 'href': '#reviews'},
            {'label': 'Операции', 'href': '#help'},
            {'label': 'Кейсы', 'href': '#cases'},
        ],
        'phone': '+7 (999) 999-99-99',
        'cta_text': 'Запись на приём',
    }
    return render(request, 'core/home.html', context)