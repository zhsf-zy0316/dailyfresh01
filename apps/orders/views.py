from datetime import datetime
from time import sleep

from django.core.urlresolvers import reverse
from django.db import transaction
from django.http.response import JsonResponse
from django.shortcuts import render, redirect
from django.views.generic import View
from django_redis import get_redis_connection
from redis.client import StrictRedis

from apps.goods.models import GoodsSKU
from apps.orders.models import OrderInfo, OrderGoods
from apps.users.models import Address
from utils.common import LoginRequiredMixin
from alipay import AliPay


class PlaceOrderView(LoginRequiredMixin, View):
    def post(self, request):

        # 获取请求参数：sku_ids，count
        count = request.POST.get('count')
        sku_ids = request.POST.getlist('sku_ids')  # 一键多值

        # 校验参数合法性
        if not sku_ids:
            # 如果商品id为空，跳转到购物车界面
            return redirect(reverse('cart:info'))

        # todo: 查询业务数据： 地址，购物车商品，总数量，总金额
        # 获取用户地址信息
        try:
            # Address.objects.filter(user=request.user).order_by('-create_time')[0]
            address = Address.objects.filter(user=request.user).latest('create_time')
        except:
            # 查询不到地址信息，则用户需要点击页面中的按钮，新增地址
            address = None

        skus = []  # 要显示的商品列表
        total_count = 0  # 商品总数量
        total_amount = 0  # 商品总金额

        strict_redis = get_redis_connection()  # type: StrictRedis
        # cart_1 = {1: 2, 2: 2}
        key = 'cart_%s' % request.user.id

        # 如果是从购物车页面过来，商品的数量从redis中获取
        if count is None:
            # 循环商品id： sku_ids
            for sku_id in sku_ids:
                # 查询商品对象
                try:
                    sku = GoodsSKU.objects.get(id=sku_id)
                except GoodsSKU.DoesNotExist:
                    # 如果商品id为空，跳转到购物车界面
                    return redirect(reverse('cart:info'))

                # 获取商品数量和小计金额(类型转换)
                count = strict_redis.hget(key, sku_id)  # bytes
                count = int(count)
                amount = sku.price * count

                # 动态地给商品对象新增实例属性(count, amount)
                sku.count = count
                sku.amount = amount

                # 添加商品对象到列表中
                skus.append(sku)

                # 累计商品总数量和总金额
                total_count += sku.count
                total_amount += sku.amount
        else:
            # 如果是从详情页面过来，商品的数量从request中获取（只有一个商品）
            sku_id = request.POST.get('sku_ids')

            # 查询商品对象
            try:
                sku = GoodsSKU.objects.get(id=sku_id)
            except GoodsSKU.DoesNotExist:
                # 如果商品id为空，跳转到购物车界面
                return redirect(reverse('cart:info'))

            # 获取商品数量和小计金额(类型转换)
            count = int(count)
            amount = sku.price * count

            # 判断库存：详情页没有判断库存
            if count > sku.stock:
                # 库存不足，跳转回详情界面
                return redirect(reverse('goods:detail', args=[sku_id]))

            # 动态地给商品对象新增实例属性(count, amount)
            sku.count = count
            sku.amount = amount

            # 添加商品对象到列表中
            skus.append(sku)

            # 累计商品总数量和总金额
            total_count += sku.count
            total_amount += sku.amount

            # 将商品数量保存到`Redis`中（以便取消操作在购物车中还能看得到商品）
            # cart_1 = {1: 2, 2: 2}
            strict_redis.hset(key, sku_id, count)

        # 运费(固定)
        trans_cost = 10
        # 实付金额
        total_pay = total_amount + trans_cost

        # 定义模板显示的字典数据

        # [1,2]  ->  1,2
        sku_ids_str = ','.join(sku_ids)

        context = {
            'skus': skus,
            'address': address,
            'total_count': total_count,
            'total_amount': total_amount,
            'trans_cost': trans_cost,
            'total_pay': total_pay,
            'sku_ids_str': sku_ids_str,
        }

        # 响应结果: 返回确认订单html界面
        return render(request, 'place_order.html', context)


class CommitOrderView(View):
    """提交订单"""

    @transaction.atomic
    def post(self, request):
        # 登录判断
        if not request.user.is_authenticated():
            return JsonResponse({'code': 1, 'message': '请先登录'})

        # 获取请求参数：address_id, pay_method, sku_ids_str
        address_id = request.POST.get('address_id')
        pay_method = request.POST.get('pay_method')
        # 商品id，格式型如： 1,2,3
        sku_ids_str = request.POST.get('sku_ids_str')

        # 校验参数不能为空
        if not all([address_id, pay_method, sku_ids_str]):
            return JsonResponse({'code': 2, 'message': '参数不完整'})

        # 判断地址是否存在
        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return JsonResponse({'code': 3, 'message': '地址不能为空'})

        # 创建保存点
        point = transaction.savepoint()
        try:
            # todo: 修改订单信息表: 保存订单数据到订单信息表中(新增一条数据)
            total_count = 0
            total_amount = 0
            trans_cost = 10

            # 时间+用户id
            order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(request.user.id)
            order = OrderInfo.objects.create(
                order_id=order_id,
                total_count=total_count,
                total_amount=total_amount,
                trans_cost=trans_cost,
                pay_method=pay_method,
                user=request.user,
                address=address,
            )

            # 获取StrictRedis对象: cart_1 = {1: 2, 2: 2}
            strict_redis = get_redis_connection()  # type: StrictRedis
            key = 'cart_%s' % request.user.id
            sku_ids = sku_ids_str.split(',')  # str ——> list

            # todo: 核心业务: 遍历每一个商品, 并保存到订单商品表
            for sku_id in sku_ids:
                # 查询订单中的每一个商品对象
                try:
                    sku = GoodsSKU.objects.get(id=sku_id)
                except GoodsSKU.DoesNotExist:
                    # 回滚动到保存点，撤销所有的sql操作
                    transaction.savepoint_rollback(point)

                    return JsonResponse({'code': 4, 'message': '商品不存在'})

                # 获取商品数量，并判断库存
                count = strict_redis.hget(key, sku_id)
                count = int(count)  # bytes -> int
                if count > sku.stock:
                    # 回滚动到保存点，撤销所有的sql操作
                    transaction.savepoint_rollback(point)
                    return JsonResponse({'code': 5, 'message': '库存不足'})

                # todo: 修改订单商品表: 保存订单商品到订单商品表（新增多条数据）
                OrderGoods.objects.create(
                    count=count,
                    price=sku.price,
                    order=order,
                    sku=sku,
                )

                # todo: 修改商品sku表: 减少商品库存, 增加商品销量
                sku.stock -= count
                sku.sales += count
                sku.save()

                # 累加商品数量和总金额
                total_count += count
                total_amount += sku.price * count

                # todo: 修改订单信息表: 修改商品总数量和总金额
            order.total_count = total_count
            order.total_amount = total_amount
            order.save()
        except:
            # 回滚动到保存点，撤销所有的sql操作
            transaction.savepoint_rollback(point)
            return JsonResponse({'code': 6, 'message': '创建订单失败'})

        # 提交事务(保存点)
        transaction.savepoint_commit(point)

        # 从Redis中删除购物车中的商品
        # cart_1 = {1: 2, 2: 2}
        # redis命令: hdel cart_1 1 2
        # 列表 -> 位置参数
        strict_redis.hdel(key, *sku_ids)

        # 订单创建成功， 响应请求，返回json
        return JsonResponse({'code': 0, 'message': '创建订单成功'})


class OrderPayView(View):
    def post(self, request):
        if not request.user.is_authenticated():
            return JsonResponse({'code': 1, 'message': '请先登录'})

        order_id = request.POST.get('order_id')
        # 校验订单id合法性
        if not order_id:
            return JsonResponse({'code': 2, 'message': '订单id不能为空'})
        # 查询订单是否存在
        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          status=1,
                                          user=request.user,
                                          )
        except OrderInfo.DoesNotExist:
            return JsonResponse({'code': 3, 'message': '订单无效'})

        app_private_key_string = open("apps/orders/app_private_key.pem").read()
        alipay_public_key_string = open("apps/orders/alipay_public_key.pem").read()

        alipay = AliPay(
            appid="2016091400513132",
            app_notify_url=None,  # 默认回调url
            app_private_key_string=app_private_key_string,
            alipay_public_key_string=alipay_public_key_string,
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            sign_type="RSA2",  # RSA 或者 RSA2   # 使用RSA测试会有问题
            debug=True  # 默认False, 如果是True表示使用沙箱环境
        )
        total_pay = order.total_amount + order.trans_cost
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,  # 订单号
            total_amount=str(total_pay),  # 注意: 不能传递total_pay
            subject="天天生鲜测试订单",
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'code': 0, 'pay_url': pay_url})


class CheckPayView(View):
    def post(self, request):
        if not request.user.is_authenticated():
            return JsonResponse({'code': 1, 'message': '请先登录'})

        # 获取请求参数: 订单id
        order_id = request.POST.get('order_id')
        # 校验订单id合法性
        if not order_id:
            return JsonResponse({'code': 2, 'message': '订单id不能为空'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          status=1,  # 表示待支付
                                          user=request.user)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'code': 3, 'message': '订单无效'})

        from alipay import AliPay
        app_private_key_string = open("apps/orders/app_private_key.pem").read()
        alipay_public_key_string = open("apps/orders/alipay_public_key.pem").read()

        alipay = AliPay(
            appid="2016091400513132",
            app_notify_url=None,  # 默认回调url
            app_private_key_string=app_private_key_string,
            alipay_public_key_string=alipay_public_key_string,
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            sign_type="RSA2",  # RSA 或者 RSA2   # 使用RSA测试会有问题
            debug=True  # 默认False, 如果是True表示使用沙箱环境
        )

        # 判断订单是否支付成功
        while (True):
            response = alipay.api_alipay_trade_query(out_trade_no=order_id)
            # 获取响应参数
            code = response.get('code')  # 响应状态码
            trade_no = response.get('trade_no')  # 支付交易号
            trade_status = response.get('trade_status')  # 订单支付状态

            if code == '10000' and trade_status == 'TRADE_SUCCESS':
                # 修改的订单的支付状态为"待评价" ("待收货")
                order.status = 4  # 待评价
                # 保存支付宝交易号到订单信息表中
                order.trade_no = trade_no
                # 修改订单
                order.save()
                # 响应请求,返回 json数据
                return JsonResponse({'code': 0, 'message': '订单支付成功'})

            elif code == '40004' or (code == '10000' and trade_status == 'WAIT_BUYER_PAY'):
                # 40004: 业务暂时处理失败,需要等待一会, 再次请求,可能就会成功
                sleep(2)
                print(code)
                continue
            else:
                # 支付失败
                print('code=%s' % code)
                print('trade_status=%s' % trade_status)
                return JsonResponse({'code': 4, 'message': '订单支付失败'})


class CommentView(LoginRequiredMixin,View):
    def get(self, request, order_id):
        # 校验参数合法性
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=request.user)
        except OrderInfo.DoesNotExist:
             return redirect(reverse("user:order"))

        order.status_desc = OrderInfo.ORDER_STATUS[order.status]
        order_skus = OrderGoods.objects.filter(order_id=order_id)

        for order_sku in order_skus:
            amount = order_sku.count * order_sku.price
            order_sku.amount = amount

        order.order_skus = order_skus

        return render(request, 'comment.html', {'order':order})

    def post(self, request, order_id):
        """订单商品评论"""
        user = request.user
        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse("user:order"))

        # 获取评论条数
        total_count = request.POST.get("total_count")
        total_count = int(total_count)

        # 循环获取订单中商品的评论内容
        for i in range(1, total_count + 1):
            # 获取评论的商品的id
            sku_id = request.POST.get("sku_%d" % i)  # sku_1 sku_2
            # 获取评论的商品的内容
            comment = request.POST.get('comment_%d' % i, '')  # comment_1 comment_2
            try:
                order_goods = OrderGoods.objects.get(order=order, sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                continue

            # 保存评论到订单商品表
            order_goods.comment = comment
            order_goods.save()

        # 修改订单的状态为“已完成”
        order.status = 5  # 已完成
        order.save()

        return redirect(reverse("user:order", args=[1]))