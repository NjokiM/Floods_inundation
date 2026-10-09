from django.urls import path

from sim import views

urlpatterns = [
    path("", views.index, name="index"),
]
