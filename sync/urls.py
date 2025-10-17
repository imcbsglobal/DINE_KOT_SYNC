from django.urls import path
from . import views

urlpatterns = [
    path("pair-check",    views.pair_check,    name="pair_check"),
    path("login",         views.login,         name="login"),
    path("verify-token",  views.verify_token,  name="verify_token"),
    path("data-download", views.data_download, name="data_download"),
    path("upload-orders", views.upload_orders, name="upload_orders"),
    path("status",        views.get_status,    name="get_status"),
    path("product-details", views.get_product_details, name="get_product_details"),
]