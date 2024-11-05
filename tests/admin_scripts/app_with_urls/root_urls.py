from django.urls import include, path

urlpatterns = [
    path(
        route="namespaced/",
        view=include("admin_scripts.app_with_urls.urls_namespaced", namespace="ns"),
    ),
    path(
        route="nons/",
        view=include("admin_scripts.app_with_urls.urls_nons")),
]
