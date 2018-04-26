from unicodedata import category

from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.http.response import HttpResponse
from django.shortcuts import render, redirect
from django.views.generic import View
from django_redis import get_redis_connection
from redis import StrictRedis

from apps.goods.models import *
from apps.users.models import User
from apps.users.views import UserAddressView


class BaseCartView(View):
    def get_cart_count(self, request):
        """获取用户购物车中商品的总数量"""
        # todo: 读取用户添加到购物车中的商品总数量
        cart_count = 0  # 购物车商品总数量
        if request.user.is_authenticated():
            # 已经登录
            strict_redis = get_redis_connection()  # type: StrictRedis
            # cart_1 = {1: 2, 2 : 2}
            key = 'cart_%s' % request.user.id
            # 返回 list类型，存储的元素是 bytes
            # [2, 2]
            vals = strict_redis.hvals(key)
            for count in vals:  # count为bytes类型
                cart_count += int(count)
        return cart_count


class IndexView(BaseCartView):
    def get(self, request):

        context = cache.get('index_page_data')
        if not context:
            categories = GoodsCategory.objects.all()

            slide_skus = IndexSlideGoods.objects.all().order_by('index')[0:4]

            promotions = IndexPromotion.objects.all().order_by('index')[0:2]

            for category in categories:
                text_skus = IndexCategoryGoods.objects.filter(
                    category=category, display_type=0).order_by('index')

                img_skus = IndexCategoryGoods.objects.filter(
                    category=category, display_type=1).order_by('index')[0:4]

                # 动态地给类别新增实例属性
                category.text_skus = text_skus
                # 动态地给类别新增实例属性
                category.img_skus = img_skus

                context = {
                    'categories': categories,
                    'slide_skus': slide_skus,
                    'promotions': promotions,
                }

                cache.set('index_page_data', context, 60 * 30)

        cart_count = self.get_cart_count(request)

        # 定义模板数据
        context.update(cart_count=cart_count)

        # 响应请求,返回html界面
        return render(request, 'index.html', context)


class DetailView(BaseCartView):
    def get(self, request, sku_id):
        categories = GoodsCategory.objects.all()
        try:
            goods_sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            # 查询不到商品则跳转到首页
            # return HttpResponse('商品不存在')
            return redirect(reverse('goods:index'))

        new_skus = GoodsSKU.objects.filter(category=goods_sku.category).order_by('-create_time')[0:2]
        other_skus = goods_sku.spu.goodssku_set.exclude(id=goods_sku.id)
        cart_count = 0

        if request.user.is_authenticated():
            cart_count = self.get_cart_count(request)

            redis_conn = get_redis_connection('default')
            key = 'history_%s' % request.user.id
            redis_conn.lrem(key, 0, goods_sku.id)
            redis_conn.lpush(key,goods_sku.id)
            redis_conn.ltrim(key, 0, 2)

        context = {
            'categories': categories,
            'goods_sku': goods_sku,
            'new_skus': new_skus,
            'cart_count': cart_count,
            'other_skus':other_skus
        }
        return render(request, 'detail.html', context)