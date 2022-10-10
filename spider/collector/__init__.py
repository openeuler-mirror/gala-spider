from spider.conf import SpiderConfig
from spider.exceptions import ConfigException
from .data_collector import DataCollector, Label, DataRecord
from .prometheus_collector import PrometheusCollector
from .aom_collector import AomCollector, AomAuth, AppCodeAuth, create_aom_collector


class DataCollectorFactory:
    @staticmethod
    def get_instance(data_source: str) -> DataCollector:
        spider_config = SpiderConfig()
        if data_source == 'prometheus':
            return PrometheusCollector(**spider_config.prometheus_conf)
        elif data_source == 'aom':
            return create_aom_collector(spider_config.aom_conf)
        raise ConfigException("Unknown data source:{}, please check!".format(data_source))
