from django.conf.urls import url, include

from apps.orders import views

urlpatterns = [
    url(r'^check$', views.CheckPayView.as_view(), name='check'),
    url(r'^comment/(.+)$', views.CommentView.as_view(), name='comment'),
    url(r'^pay$', views.OrderPayView.as_view(), name='pay'),
    url(r'^place$', views.PlaceOrderView.as_view(), name='place'),
    url(r'^commit$', views.CommitOrderView.as_view(), name='commit'),
]
