from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("productos/", views.product_list, name="products"),
    path("clientes/", views.customers, name="customers"),
    path("sync/", views.trigger_sync, name="sync"),
]
