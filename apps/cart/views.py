from django.core.urlresolvers import reverse
from django.http import JsonResponse
from django.shortcuts import render, redirect

# Create your views here.
from django.views.generic import View
from django_redis import get_redis_connection

from apps.goods.models import GoodsSKU
from utils.common import LoginRequiredMixin


class CartInfoView(LoginRequiredMixin, View):
    def get(self, request):
        user_id = request.user.id

        strict_redis = get_redis_connection()  # type:  strict_redis
        key = 'cart_%s' % user_id
        sku_ids = strict_redis.hkeys(key)

        # 保存购物车中所有的商品对象
        skus = []
        # 商品总数量
        total_count = 0
        # 商品总金额
        total_amount = 0

        for sku_id in sku_ids:
            sku = GoodsSKU.objects.get(id=int(sku_id))

            count = strict_redis.hget(key, sku_id)
            amount = sku.price * int(count)
            sku.count = int(count)
            sku.amount = amount
            total_count += sku.count
            total_amount += sku.amount
            skus.append(sku)

        context = {
            'skus': skus,
            'total_count': total_count,
            'total_amount': total_amount,
        }
        return render(request, 'cart.html', context)


class CartAddView(LoginRequiredMixin, View):
    def post(self, request):
        if not request.user.is_authenticated():
            return JsonResponse({'code': 1, 'errmsg': '请先登录'})

        user_id = request.user.id
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # todo: 判断参数合法性
        if not all([sku_id, count]):
            return JsonResponse({'code': 2, 'errmsg': '请求参数不能为空'})

        try:
            count = int(count)
        except:
            return JsonResponse({'code': 3, 'errmsg': '购买数量格式不正确'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'code': 4, 'errmsg': '商品不存在'})

        strict_redis = get_redis_connection()
        key = 'cart_%s' % user_id
        # 获取不到会返回None
        val = strict_redis.hget(key, sku_id)
        if val:
            count += int(val)

        if count > sku.stock:
            return JsonResponse({'code': 5, 'errmsg': '库存不足'})

        strict_redis.hset(key, sku_id, count)

        # todo: 计算购物车中商品的总数量
        cart_count = 0
        vals = strict_redis.hvals(key)
        for val in vals:
            cart_count += int(val)

        return JsonResponse({'code': 0, 'message': '添加到购物车成功',
                             'cart_count': cart_count})


class CartDeleteView(View):
    def post(self, request):
        if not request.user.is_authenticated():
            return JsonResponse({'code': 1, 'errmsg': '请先登录'})
        sku_id = request.POST.get('sku_id')
        if not sku_id:
            return JsonResponse({'code': 2, 'errmsg': '商品id不能为空'})
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'code': 3, 'errmsg': '商品不存在'})
        strict_redis = get_redis_connection()  # type:  strict_redis
        key = 'cart_%s' % request.user.id
        strict_redis.hdel(key, sku_id)

        return JsonResponse({'code': 0, 'message': '删除商品成功'})


class UpdateCartView(View):
    """更新购物车数据：+ -"""

    def post(self, request):
        if not request.user.is_authenticated():
            return JsonResponse({'code': 1, 'errmsg': '请先登录'})
        # 获取参数：sku_id, count
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')
        # 校验参数all()
        if not all([sku_id,count]):
            return JsonResponse({'code': 2, 'errmsg': '请求参数不能为空'})

        # 判断商品是否存在

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'code': 3, 'errmsg': '商品不存在'})

        # 判断count是否是整数
        try:
            count = int(count)
        except Exception:
            return JsonResponse({'code': 4, 'errmsg': '购买数量格式不正确'})
        # 判断库存
        if count > sku.stock:
            return JsonResponse({'code': 5, 'errmsg': '库存不足'})
        # 如果用户登陆，将修改的购物车数据存储到redis中
        strict_redis = get_redis_connection()  # type:  strict_redis
        key = 'cart_%s' % request.user.id
        strict_redis.hset(key,sku_id,count)
        # 并响应请求
        total_count = 0  # 购物车商品总数量
        vals = strict_redis.hvals(key)  # 列表 bytes
        for val in vals:
            total_count += int(val)  # bytes -> int
        return JsonResponse({'code': 0, 'message': '修改商品数量成功',
                             'total_count': total_count})