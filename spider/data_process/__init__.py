from spider.collector import DataCollectorFactory
from .processor import DataProcessor
from .prometheus_processor import PrometheusProcessor


class DataProcessorFactory:
    @staticmethod
    def get_instance(data_source: str) -> DataProcessor:
        collector = DataCollectorFactory.get_instance(data_source)
        return PrometheusProcessor(collector)
