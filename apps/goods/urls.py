from django.conf.urls import url, include

from apps.goods import views

urlpatterns = [

    url('^index$', views.IndexView.as_view(), name='index'),
    url('^index$', views.IndexView.as_view(), name='index'),
    url(r'^detail/(?P<sku_id>\d+)$', views.DetailView.as_view(), name='detail'),
]
