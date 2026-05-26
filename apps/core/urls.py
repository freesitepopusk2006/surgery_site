from django.urls import path
from .views import home_view, patient_page_detail_view, patients_view, prices_view

app_name = 'core'

urlpatterns = [
    path('', home_view, name='home'),
    path('prices/', prices_view, name='prices'),
    path('patients/', patients_view, name='patients'),
    path('patients/<slug:slug>/', patient_page_detail_view, name='patient_page_detail'),
]
