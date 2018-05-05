from django.conf.urls import url, include

from apps.goods import views

urlpatterns = [

    url('^index$', views.IndexView.as_view(), name='index'),
    url(r'^detail/(\d+)$', views.DetailView.as_view(), name='detail'),
    url(r'^list/(?P<category_id>\d+)/(?P<page_num>\d+)$',views.ListView.as_view(), name='list'),
]
