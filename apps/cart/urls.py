from django.conf.urls import url, include

from apps.cart import views

urlpatterns = [

    url(r'^add$', views.CartAddView.as_view(), name='add'),
    url(r'^info$', views.CartInfoView.as_view(), name='info'),
    url(r'^delete$', views.CartDeleteView.as_view(), name='delete'),
    url(r'^update$', views.UpdateCartView.as_view(), name='update'),
]
