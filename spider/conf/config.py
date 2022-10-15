import os

import yaml

from spider.util.singleton import Singleton
from spider.util import logger


class SpiderConfig(metaclass=Singleton):
    def __init__(self):
        super().__init__()
        self.db_agent = None
        self.data_agent = None
        self.observe_conf_path = None

        self.log_conf = {
            'log_path': '/var/log/gala-spider/spider.log',
            'log_level': 'INFO',
            'max_size': 10,
            'backup_count': 10,
        }

        self.kafka_conf = {
            'server': None,
            'metadata_topic': None,
            'metadata_group_id': None,
        }

        self.prometheus_conf = {
            'base_url': None,
            'instant_api': None,
            'range_api': None,
            'step': 5,
        }

        self.storage_conf = {
            'period': 60,   # unit: minute
            'database': 'arangodb',
            'db_conf': {
                'url': None,
                'db_name': None,
            }
        }

        self.aom_conf = {
            'base_url': '',
            'project_id': '',
            'step': 5,
            'auth_type': 'appcode',
            'auth_info': {},
        }

    def load_from_yaml(self, conf_path: str) -> bool:
        try:
            real_path = os.path.realpath(conf_path)
            with open(real_path, 'rb') as file:
                result = yaml.safe_load(file.read())
        except IOError as ex:
            logger.logger.error('Unable to load config file: {}'.format(ex))
            return False

        global_conf = result.get('global', {})
        self.db_agent = global_conf.get('data_source')
        self.data_agent = global_conf.get('data_agent')
        self.observe_conf_path = global_conf.get('observe_conf_path')

        spider_conf = result.get('spider', {})
        self.log_conf.update(spider_conf.get('log_conf', {}))

        self.kafka_conf.update(result.get('kafka', {}))
        self.prometheus_conf.update(result.get('prometheus', {}))

        self.storage_conf.update(result.get('storage', {}))

        self.aom_conf.update(result.get('aom', {}))
        auth_info = self.aom_conf.get('auth_info', {})
        ssl_verify = True
        if auth_info.get('ssl_verify', 0) == 0:
            ssl_verify = False
        auth_info.update({'ssl_verify': ssl_verify})

        return True


def init_spider_config(spider_conf_path) -> bool:
    logger.logger.info('Spider config init')
    spider_config = SpiderConfig()
    if not spider_config.load_from_yaml(spider_conf_path):
        logger.logger.error('Load spider config failed.')
        return False
    logger.logger.info('Load spider config success.')
    return True
