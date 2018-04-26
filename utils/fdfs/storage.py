from django.core.files.storage import FileSystemStorage
from fdfs_client.client import Fdfs_client


class FdfsStorage(FileSystemStorage):

    def _save(self, name, content):
        # path = super()._save(name, content)

        client = Fdfs_client('client.conf')

        try:
            datas = content.read()

            dict_data = client.upload_by_buffer(datas)

            if 'Upload successed.' != dict_data.get('Status'):
                raise Exception('上传文件到FastDFS失败, Status不正确.')
            path = dict_data
        except Exception as e:
            raise e

        return path

    def url(self, name):
        """返回图片显示时的url地址"""

        # 此url的值为: 数据库中保存的url路径的值
        url = super().url(name)
        # print(url)
        return 'http://127.0.0.1:8888/' + url