from spider.conf import SpiderConfig
from spider.collector import DataCollectorFactory
from .processor import DataProcessor
from .prometheus_processor import PrometheusProcessor


class DataProcessorFactory:
    @staticmethod
    def get_instance(data_source: str) -> DataProcessor:
        spider_config = SpiderConfig()
        conf = {}
        if data_source == 'prometheus':
            conf = spider_config.prometheus_conf
        elif data_source == 'aom':
            conf = spider_config.aom_conf
        collector = DataCollectorFactory.get_instance(data_source, conf)
        return PrometheusProcessor(collector)
