from django.urls import path
from .views import home_view, patients_view, prices_view

app_name = 'core'

urlpatterns = [
    path('', home_view, name='home'),
    path('prices/', prices_view, name='prices'),
    path('patients/', patients_view, name='patients'),
]
