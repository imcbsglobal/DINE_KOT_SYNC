from django.urls import path
from . import views

urlpatterns = [
    path("pair-check",    views.pair_check,    name="pair_check"),
    path("login",         views.login,         name="login"),
    path("verify-token",  views.verify_token,  name="verify_token"),
    path("status",        views.get_status,    name="get_status"),
    path("items/", views.get_items, name="get_items"),
    path("dine-tables/", views.get_dine_tables, name="get_dine_tables"),
    path("user-settings/", views.get_user_settings, name="get_user_settings"),
    path("dine-categories/", views.get_dine_categories, name="get_dine_categories"),

]