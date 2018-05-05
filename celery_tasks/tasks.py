# 在celery服务器所在的项目中，
# 需要手动添加如下代码，初始化django环境
# import os
# import django
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dailyfresh.settings")
# django.setup()
from time import sleep

from celery import Celery
from django.core.mail import send_mail
from django.template import loader

from apps.goods.models import *
from dailyfresh import settings

# 创建celery客户端
# 参数1：自定义名称
# 参数２：中间人
app = Celery('dailyfresh', broker='redis://127.0.0.1:6379/1')


@app.task
def send_active_mail(username, email, token):
    """发送激活邮件"""
    subject = '天天生鲜激活邮件'         # 标题，必须指定
    message = ''                       # 正文
    from_email = settings.EMAIL_FROM   # 发件人
    recipient_list = [email]           # 收件人
    # 正文 （带有html样式）
    html_message = ('<h3>尊敬的%s：感谢注册天天生鲜</h3>'
                    '请点击以下链接激活您的帐号:<br/>'
                    '<a href="http://127.0.0.1:8000/users/active/%s">'
                    'http://127.0.0.1:8000/users/active/%s</a>'
                    ) % (username, token, token)

    send_mail(subject, message, from_email, recipient_list,
              html_message=html_message)
    pass


@app.task
def generate_static_index_html():
    sleep(2)
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
        category.image_skus = img_skus

    cart_count = 0

    # 定义模板数据
    context = {
        'categories': categories,
        'slide_skus': slide_skus,
        'promotions': promotions,
        'cart_count': cart_count,
    }

    template = loader.get_template('index.html')

    html_str = template.render(context)

    path = '/home/python/Desktop/static/index.html'

    with open(path,'w') as file:
        file.write(html_str)