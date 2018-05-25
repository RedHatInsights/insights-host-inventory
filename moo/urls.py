"""moo URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings

from dynamic_rest.routers import DynamicRouter
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from inventory import views

router = DynamicRouter()
router.register("entities", views.EntityViewSet)
router.register("tags", views.TagViewSet)


schema_view = get_schema_view(
    openapi.Info(
        title="Inventory API",
        default_version='v1',
        description="Inventory Service API",
        contact=openapi.Contact(email="insights-dev@redhat.com"),
        license=openapi.License(name="Apache 2 License"),
    ),
    # validators=['flex', 'ssv'],
    public=True
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include(router.urls)),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    re_path(r'^swagger(?P<format>\.json|\.yaml)$',
         schema_view.without_ui(cache_timeout=None), name='schema-json'),
    re_path(r'^swagger/$',
         schema_view.with_ui('swagger', cache_timeout=None), name='schema-swagger-ui'),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [path("__debug__", include(debug_toolbar.urls))] + urlpatterns
