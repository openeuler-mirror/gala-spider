from spider.exceptions import ConfigException
from .data_collector import DataCollector, Label, DataRecord
from .prometheus_collector import create_prom_collector
from .aom_collector import AomCollector, AomAuth, AppCodeAuth, create_aom_collector


class DataCollectorFactory:
    @staticmethod
    def get_instance(data_source: str, conf: dict) -> DataCollector:
        if data_source == 'prometheus':
            return create_prom_collector(conf)
        elif data_source == 'aom':
            return create_aom_collector(conf)
        raise ConfigException("Unknown data source:{}, please check!".format(data_source))
