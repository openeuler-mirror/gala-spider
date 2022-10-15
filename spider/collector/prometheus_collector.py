from typing import List

import requests

from spider.util import logger
from .data_collector import DataCollector, DataRecord, Label


def generate_query_sql(metric_id: str, query_options: dict = None) -> str:
    if query_options is None:
        return metric_id

    sql = "{}{{".format(metric_id)
    for key, val in query_options.items():
        sql += "{key}=\"{val}\", ".format(key=key, val=val)
    sql += "}"
    return sql


class PrometheusCollector(DataCollector):
    def __init__(self, base_url: str = None, instant_api: str = None, range_api: str = None, step: int = None):
        super().__init__()
        self._base_url = base_url
        self._instant_api = instant_api
        self._range_api = range_api
        self._step = step

    @staticmethod
    def set_instant_query_params(metric_id: str, query_options: dict, timestamp: float) -> dict:
        params = {
            "query": generate_query_sql(metric_id, query_options),
        }
        if timestamp is not None:
            params["time"] = timestamp
        return params

    @staticmethod
    def set_range_query_params(metric_id: str, start: float, end: float, step: int, query_options: dict) -> dict:
        params = {
            "query": generate_query_sql(metric_id, query_options),
            "start": start,
            "end": end,
            "step": step
        }
        return params

    @staticmethod
    def query(req_data: dict) -> list:
        url = req_data.get('url')
        params = req_data.get('params')
        headers = req_data.get('headers')

        try:
            resp = requests.get(url, params, headers=headers).json()
        except requests.RequestException as ex:
            logger.logger.error(ex)
            return []

        result = []
        if resp is not None and resp.get('status') == 'success':
            result = resp.get('data', {}).get('result', [])
        else:
            logger.logger.warning("Failed to request {}, error is: {}".format(url, resp))
        return result

    @staticmethod
    def transfer_instant_data(instant_data: list) -> List[DataRecord]:
        records = []
        for item in instant_data:
            metric = item.get("metric", {})
            value = item.get("value", [])
            if not metric or not value:
                continue
            labels = [Label(k, v) for k, v in metric.items()]
            records.append(DataRecord(metric.get('__name__'), value[0], value[1], labels))
        return records

    @staticmethod
    def transfer_range_data(range_data: list) -> List[DataRecord]:
        records = []
        for item in range_data:
            metric = item.get("metric", {})
            values = item.get("values", [])
            if not metric or not values:
                continue
            labels = [Label(k, v) for k, v in metric.items()]
            for value in values:
                records.append(DataRecord(metric.get('__name__'), value[0], value[1], labels))
        return records

    def get_instant_data(self, metric_id: str, timestamp: float = None, **kwargs) -> List[DataRecord]:
        req_data = self.set_instant_req_info(metric_id, timestamp, **kwargs)
        data = self.query(req_data)
        if len(data) == 0:
            logger.logger.debug("No data collected, metric id is: {}".format(metric_id))
        return self.transfer_instant_data(data)

    def get_range_data(self, metric_id: str, start: float, end: float, **kwargs) -> List[DataRecord]:
        req_data = self.set_range_req_info(metric_id, start, end, **kwargs)
        data = self.query(req_data)
        if len(data) == 0:
            logger.logger.debug("No data collected, metric id is: {}".format(metric_id))
        return self.transfer_range_data(data)

    def set_instant_req_info(self, metric_id: str, timestamp: float, **kwargs) -> dict:
        req_data = {'url': self._base_url + self._instant_api}
        query_options = kwargs.get("query_options")
        params = self.set_instant_query_params(metric_id, query_options, timestamp)
        req_data.update({'params': params})
        return req_data

    def set_range_req_info(self, metric_id: str, start: float, end: float, **kwargs) -> dict:
        req_data = {'url': self._base_url + self._range_api}
        query_options = kwargs.get("query_options")
        step = kwargs.get("step") if "step" in kwargs else self._step
        params = self.set_range_query_params(metric_id, start, end, step, query_options)
        req_data.update({'params': params})
        return req_data


def create_prom_collector(prom_conf: dict) -> PrometheusCollector:
    return PrometheusCollector(
        base_url=prom_conf.get('base_url'),
        instant_api=prom_conf.get('instant_api'),
        range_api=prom_conf.get('range_api'),
        step=prom_conf.get('step')
    )
