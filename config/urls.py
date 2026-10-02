from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path

from inventory.views import LandingView, quick_move, report

urlpatterns = [
    path('', LandingView.as_view(), name='landing'),
    path('logout/', LogoutView.as_view(next_page='landing'), name='logout'),
    path('inventory/quick-move/', quick_move, name='quick_move'),
    path('inventory/reports/<str:kind>/', report, name='report'),
    path('admin/', admin.site.urls),
]
