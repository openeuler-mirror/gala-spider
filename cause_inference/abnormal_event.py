import json
from enum import Enum
from queue import Queue, Empty
from typing import List

from kafka import KafkaConsumer

from spider.util import logger
from spider.conf.observe_meta import ObserveMetaMgt
from cause_inference.exceptions import DataParseException
from cause_inference.exceptions import NoKpiEventException
from cause_inference.model import AbnormalEvent


class AbnEvtType(Enum):
    APP = 'app'
    SYS = 'sys'


class AbnEvtMgt:
    def __init__(self, kpi_consumer: KafkaConsumer, metric_consumer: KafkaConsumer,
                 valid_duration, future_duration, aging_duration):
        self.kpi_consumer = kpi_consumer
        self.metric_consumer = metric_consumer
        self.valid_duration = valid_duration * 1000
        self.future_duration = future_duration * 1000
        self.aging_duration = aging_duration * 1000

        self.all_metric_evts: List[AbnormalEvent] = []
        self.kpi_queue: Queue = Queue()
        self.last_kpi_evt_ts = 0
        self.last_metric_evt_ts = 0

    def get_abnormal_info(self) -> (AbnormalEvent, List[AbnormalEvent]):
        try:
            abn_kpi = self.kpi_queue.get_nowait()
        except Empty as ex:
            raise NoKpiEventException from ex

        self.consume_kpi_evts_with_deadline(abn_kpi.timestamp)
        self.consume_metric_evts_with_deadline(abn_kpi.timestamp)
        self.clear_aging_evts(abn_kpi.timestamp)
        metric_evts = self.filter_valid_evts(abn_kpi.timestamp)

        return abn_kpi, metric_evts

    def process_kpi_evt(self, data):
        try:
            abn_evt = parse_abn_evt(data)
        except DataParseException as ex:
            logger.logger.error(ex)
            return
        if not abn_evt.update_entity_id(ObserveMetaMgt()):
            logger.logger.warning("Can't identify entity id of the abnormal kpi {}".format(abn_evt.abnormal_metric_id))
            return

        self.all_metric_evts.append(abn_evt)
        evt_type = data.get('Attributes', {}).get('event_type')
        if evt_type == AbnEvtType.APP.value:
            self.kpi_queue.put(abn_evt)

        metric_evts = parse_recommend_metric_evts(data)
        self.all_metric_evts.extend(metric_evts)

    def consume_kpi_evts(self):
        for msg in self.kpi_consumer:
            try:
                data = json.loads(msg.value)
            except (ValueError, TypeError) as ex:
                logger.logger.warning(ex)
                continue
            self.process_kpi_evt(data)

            self.last_kpi_evt_ts = max(self.last_kpi_evt_ts, data.get('Timestamp'))
            if not self.kpi_queue.empty():
                return

    def consume_kpi_evts_with_deadline(self, cur_ts):
        if self.is_future(self.last_kpi_evt_ts, cur_ts):
            return
        for msg in self.kpi_consumer:
            try:
                data = json.loads(msg.value)
            except (ValueError, TypeError) as ex:
                logger.logger.warning(ex)
                continue
            self.process_kpi_evt(data)

            evt_ts = data.get('Timestamp')
            self.last_kpi_evt_ts = max(self.last_kpi_evt_ts, evt_ts)
            if self.is_future(evt_ts, cur_ts):
                break

    def process_metric_evt(self, data):
        try:
            metric_evt = parse_abn_evt(data)
        except DataParseException as ex:
            logger.logger.warning(ex)
            return
        if not metric_evt.update_entity_id(ObserveMetaMgt()):
            logger.logger.debug("Can't identify entity id of the metric {}".format(metric_evt.abnormal_metric_id))
            return

        self.all_metric_evts.append(metric_evt)

    def consume_metric_evts_with_deadline(self, cur_ts):
        if self.is_future(self.last_metric_evt_ts, cur_ts):
            return
        for msg in self.metric_consumer:
            try:
                data = json.loads(msg.value)
            except (ValueError, TypeError) as ex:
                logger.logger.error(ex)
                continue
            evt_ts = data.get('Timestamp')
            self.last_kpi_evt_ts = max(self.last_metric_evt_ts, evt_ts)
            if self.is_aging(evt_ts, cur_ts):
                continue
            self.process_metric_evt(data)
            if self.is_future(evt_ts, cur_ts):
                break

    def filter_valid_evts(self, cur_ts):
        res = []
        for evt in self.all_metric_evts:
            if not self.is_valid(evt.timestamp, cur_ts):
                continue
            res.append(evt)
        return res

    def clear_aging_evts(self, cur_ts):
        res = []
        for evt in self.all_metric_evts:
            if self.is_aging(evt.timestamp, cur_ts):
                continue
            res.append(evt)
        self.all_metric_evts = res

    def is_valid(self, evt_ts, cur_ts):
        return cur_ts - self.valid_duration < evt_ts <= cur_ts + self.future_duration

    def is_aging(self, evt_ts, cur_ts):
        return evt_ts + self.aging_duration < cur_ts

    def is_future(self, evt_ts, cur_ts):
        return evt_ts > cur_ts + self.future_duration


def preprocess_abn_score(score):
    return max(0, score)


def parse_abn_evt(data) -> AbnormalEvent:
    resource = data.get('Resource', {})
    attrs = data.get('Attributes', {})
    if not resource.get('metric') and not resource.get('metrics'):
        raise DataParseException('Attribute "Resource.metric" required in abnormal event')
    if not attrs.get('entity_id') and not resource.get('labels'):
        raise DataParseException('Metric labels or entity id required in abnormal event')
    abn_evt = AbnormalEvent(
        timestamp=data.get('Timestamp'),
        abnormal_metric_id=resource.get('metric') or resource.get('metrics'),
        abnormal_score=preprocess_abn_score(resource.get('score', 0.0)),
        metric_labels=resource.get('labels'),
        abnormal_entity_id=attrs.get('entity_id'),
        desc=resource.get('description', '') or data.get('Body', ''),
        event_id=attrs.get('event_id')
    )
    return abn_evt


def parse_recommend_metric_evts(abn_kpi_data: dict) -> List[AbnormalEvent]:
    metric_evts = []
    obsv_meta_mgt = ObserveMetaMgt()
    recommend_metrics = abn_kpi_data.get('Resource', {}).get('cause_metrics', {})
    event_id = abn_kpi_data.get('Attributes', {}).get('event_id')
    for metric_data in recommend_metrics:
        metric_evt = AbnormalEvent(
            timestamp=int(float(abn_kpi_data.get('Timestamp'))),
            abnormal_metric_id=metric_data.get('metric', ''),
            abnormal_score=preprocess_abn_score(metric_data.get('score', 0.0)),
            metric_labels=metric_data.get('labels', {}),
            desc=metric_data.get('description', ''),
            event_id=event_id
        )
        if not metric_evt.update_entity_id(obsv_meta_mgt):
            logger.logger.debug("Can't identify entity id of the metric {}".format(metric_evt.abnormal_metric_id))
            continue
        metric_evts.append(metric_evt)
    return metric_evts
