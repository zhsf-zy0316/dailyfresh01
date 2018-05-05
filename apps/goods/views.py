from unicodedata import category

from django.core.cache import cache
from django.core.paginator import Paginator, EmptyPage
from django.core.urlresolvers import reverse
from django.http.response import HttpResponse
from django.shortcuts import render, redirect
from django.views.generic import View
from django_redis import get_redis_connection
from redis import StrictRedis

from apps.goods.models import *
from apps.orders.models import OrderGoods
from apps.users.models import User
from apps.users.views import UserAddressView


class BaseCartView(View):
    def get_cart_count(self, request):
        """获取用户购物车中商品的总数量"""
        # todo: 读取用户添加到购物车中的商品总数量
        cart_count = 0
        if request.user.is_authenticated():

            strict_redis = get_redis_connection()  # type: StrictRedis

            key = 'cart_%s' % request.user.id

            vals = strict_redis.hvals(key)
            for count in vals:  # count为bytes类型
                cart_count += int(count)
        return cart_count


class IndexView(BaseCartView):

    def get2(self, request):
        print(UserAddressView.__mro__)

        # 显示登录的用户名
        # 方式1：主动查询登录用户并显示
        # user_id = request.session.get('_auth_user_id')
        # user = User.objects.get(id=user_id)
        # context = {'user': user}
        # return render(request, 'index.html', context)

        # 方式2：使用django用户认证模块，直接显示
        # django会自动查询登录的用户对象，会保存到request对象中
        # 并且会把user对象传递给模块
        # user = request.user
        return render(request, 'index.html')

    def get(self, request):
        # 读取Redis中的缓存数据
        context = cache.get('index_page_data')
        if not context:
            print('没有缓存，从mysql数据库中读取')
            # 查询首页商品数据：商品类别，轮播图， 促销活动
            categories = GoodsCategory.objects.all()
            slide_skus = IndexSlideGoods.objects.all().order_by('index')
            promotions = IndexPromotion.objects.all().order_by('index')[0:2]
            # category_skus = IndexCategoryGoods.objects.all()

            for c in categories:
                # 查询当前类型所有的文字商品和图片商品
                text_skus = IndexCategoryGoods.objects.filter(
                    display_type=0, category=c)
                image_skus = IndexCategoryGoods.objects.filter(
                    display_type=1, category=c)[0:4]
                # 动态给对象新增实例属性
                c.text_skus = text_skus
                c.image_skus = image_skus

            # 定义要缓存的数据： 字典
            context = {
                'categories': categories,
                'slide_skus': slide_skus,
                'promotions': promotions,
            }

            # 缓存数据：保存数据到Redis中
            # 参数1： 键名
            # 参数2： 要缓存的数据（字典）
            # 参数3： 缓存时间：半个小时
            cache.set('index_page_data', context, 60*30)
        else:
            print('使用缓存')

        # 获取用户添加到购物车商品的总数量
        cart_count = self.get_cart_count(request)
        # cart_count = super().get_cart_count(request)

        # 定义模板显示的数据
        # 给字典新增一个键值
        context['cart_count'] = cart_count
        # context.update({'cart_count': cart_count})
        # context.update(cart_count=cart_count)

        # 响应请求
        return render(request, 'index.html', context)


class DetailView(BaseCartView):
    def get(self, request, sku_id):
        categories = GoodsCategory.objects.all()
        try:
            goods_sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:

            return redirect(reverse('goods:index'))

        new_skus = GoodsSKU.objects.filter(category=goods_sku.category).order_by('-create_time')[0:2]
        other_skus = goods_sku.spu.goodssku_set.exclude(id=goods_sku.id)
        cart_count = 0
        order_skus = OrderGoods.objects.filter(sku=goods_sku).exclude(comment='')

        if request.user.is_authenticated():
            cart_count = self.get_cart_count(request)

            redis_conn = get_redis_connection('default')
            key = 'history_%s' % request.user.id
            redis_conn.lrem(key, 0, goods_sku.id)
            redis_conn.lpush(key, goods_sku.id)
            redis_conn.ltrim(key, 0, 2)

        context = {
            'categories': categories,
            'goods_sku': goods_sku,
            'new_skus': new_skus,
            'cart_count': cart_count,
            'other_skus': other_skus,
            'order_skus': order_skus
        }
        return render(request, 'detail.html', context)


class ListView(BaseCartView):
    def get(self, request, category_id, page_num):
        sort = request.GET.get('sort', 'default')
        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return redirect(reverse('goods:index'))
        if sort == 'price':

            skus = GoodsSKU.objects.filter(category=category).order_by('price')
        elif sort == 'hot':

            skus = GoodsSKU.objects.filter(category=category).order_by('-sales')
        else:
            skus = GoodsSKU.objects.filter(category=category)

            sort = 'default'
        categories = GoodsCategory.objects.all()
        new_skus = GoodsSKU.objects.filter(category=category).order_by('-create_time')[0:2]
        cart_count = 0

        if request.user.is_authenticated():
            cart_count = self.get_cart_count(request)

        page_num = int(page_num)

        paginator = Paginator(skus, 2)

        try:
            page = paginator.page(page_num)
        except EmptyPage:

            page = paginator.page(1)

        page_list = paginator.page_range

        context = {
            'category': category,
            'categories': categories,
            'page_list': page_list,
            'page': page,
            'new_skus': new_skus,
            'cart_count': cart_count,
            'sort': sort
        }

        return render(request, 'list.html', context)
