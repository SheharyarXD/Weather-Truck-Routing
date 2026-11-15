from django.urls import include, path, re_path

from routing.views import spa_index

urlpatterns = [
    path("api/", include("routing.urls")),
    # Everything that is not the API or a static asset is the single-page app.
    re_path(r"^(?!api/|static/).*$", spa_index, name="spa"),
]
