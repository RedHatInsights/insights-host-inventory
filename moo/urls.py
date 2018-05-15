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
from django.urls import path, include
from django.conf import settings

from rest_framework import routers
from rest_framework_swagger.views import get_swagger_view

from graphene_django.views import GraphQLView

from inventory import views

router = routers.DefaultRouter()
router.register("entities", views.EntityViewSet)
router.register("facts", views.FactViewSet)
router.register("tags", views.TagViewSet)
router.register("ids", views.AlternativeIdViewSet)

schema_view = get_swagger_view(title="Inventory API")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("account/<str:account_number>/", include(router.urls)),
    path("", include(router.urls)),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("api", schema_view),
    path("graphql", GraphQLView.as_view(graphiql=True)),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path("__debug__", include(debug_toolbar.urls))] + urlpatterns
