import json
import os
import threading
import time

from kafka import KafkaConsumer
from kafka import KafkaProducer
from kafka.errors import KafkaTimeoutError

from spider.util import logger
from spider.conf import init_observe_meta_config
from spider.conf.observe_meta import ObserveMetaMgt
from cause_inference.config import infer_config
from cause_inference.config import init_infer_config
from cause_inference.cause_infer import cause_locating
from cause_inference.rule_parser import rule_engine
from cause_inference.exceptions import InferenceException
from cause_inference.exceptions import NoKpiEventException
from cause_inference.abnormal_event import AbnEvtMgt
from cause_inference.output import gen_cause_msg
from cause_inference.cause_keyword import cause_keyword_mgt

INFER_CONFIG_PATH = '/etc/gala-inference/gala-inference.yaml'
EXT_OBSV_META_PATH = '/etc/gala-inference/ext-observe-meta.yaml'
RULE_META_PATH = '/etc/gala-inference/infer-rule.yaml'
CAUSE_KEYWORD_PATH = '/etc/gala-inference/cause-keyword.yaml'

ABN_KPI_POLL_INTERVAL_SEC = 30


def init_config():
    conf_path = os.environ.get('INFER_CONFIG_PATH') or INFER_CONFIG_PATH
    if not init_infer_config(conf_path):
        return False
    logger.init_logger('gala-inference', infer_config.log_conf)

    if not init_observe_meta_config(infer_config.data_agent, EXT_OBSV_META_PATH):
        logger.logger.error('Load observe metadata failed.')
        return False
    logger.logger.info('Load observe metadata success.')

    if not rule_engine.load_rule_meta_from_yaml(RULE_META_PATH):
        logger.logger.error('Load rule meta failed.')
        return False
    logger.logger.info('Load rule meta success.')

    if not cause_keyword_mgt.load_keywords_from_yaml(CAUSE_KEYWORD_PATH):
        logger.logger.error('Load cause keyword failed.')
        return False
    logger.logger.info('Load cause keyword success.')

    return True


class ObsvMetaCollThread(threading.Thread):
    def __init__(self, observe_meta_mgt: ObserveMetaMgt, metadata_consumer):
        super().__init__()
        self.observe_meta_mgt = observe_meta_mgt
        self.metadata_consumer = metadata_consumer

    def run(self):
        for msg in self.metadata_consumer:
            data = json.loads(msg.value)
            metadata = {}
            metadata.update(data)
            self.observe_meta_mgt.add_observe_meta_from_dict(metadata)

def config_kafka_sasl_plaintext(conf):
    conf['security_protocol'] = "SASL_PLAINTEXT"
    conf['sasl_mechanism'] = "PLAIN"
    conf['sasl_plain_username'] = infer_config.kafka_conf.get("username")
    conf['sasl_plain_password'] = infer_config.kafka_conf.get("password")

def init_metadata_consumer():
    metadata_topic = infer_config.kafka_conf.get('metadata_topic')
    conf = {
        "bootstrap_servers": [infer_config.kafka_conf.get('server')],
        "group_id": metadata_topic.get('group_id')
    }
    if infer_config.kafka_conf.get('auth_type') == 'sasl_plaintext':
        config_kafka_sasl_plaintext(conf)
    metadata_consumer = KafkaConsumer(
        metadata_topic.get('topic_id'),
        **conf
    )
    return metadata_consumer


def init_kpi_consumer():
    kpi_kafka_conf = infer_config.kafka_conf.get('abnormal_kpi_topic')
    conf = {
        "bootstrap_servers": [infer_config.kafka_conf.get('server')],
        "group_id": kpi_kafka_conf.get('group_id'),
        "consumer_timeout_ms": kpi_kafka_conf.get('consumer_to') * 1000
    }
    if infer_config.kafka_conf.get('auth_type') == 'sasl_plaintext':
        config_kafka_sasl_plaintext(conf)
    kpi_consumer = KafkaConsumer(
        kpi_kafka_conf.get('topic_id'),
        **conf
    )
    return kpi_consumer


def init_metric_consumer():
    metric_kafka_conf = infer_config.kafka_conf.get('abnormal_metric_topic')
    conf = {
        "bootstrap_servers": [infer_config.kafka_conf.get('server')],
        "group_id": metric_kafka_conf.get('group_id'),
        "consumer_timeout_ms": metric_kafka_conf.get('consumer_to') * 1000
    }
    if infer_config.kafka_conf.get('auth_type') == 'sasl_plaintext':
        config_kafka_sasl_plaintext(conf)
    metric_consumer = KafkaConsumer(
        metric_kafka_conf.get('topic_id'),
        **conf
    )
    return metric_consumer


def init_cause_producer():
    conf = {
        "bootstrap_servers": [infer_config.kafka_conf.get('server')]
    }
    if infer_config.kafka_conf.get('auth_type') == 'sasl_plaintext':
        config_kafka_sasl_plaintext(conf)
    cause_producer = KafkaProducer(**conf)
   
    return cause_producer


def init_abn_evt_mgt():
    kpi_consumer = init_kpi_consumer()
    metric_consumer = init_metric_consumer()
    valid_duration = infer_config.infer_conf.get('evt_valid_duration')
    future_duration = infer_config.infer_conf.get('evt_future_duration')
    aging_duration = infer_config.infer_conf.get('evt_aging_duration')
    abn_evt_mgt = AbnEvtMgt(kpi_consumer, metric_consumer, valid_duration=valid_duration,
                            aging_duration=aging_duration, future_duration=future_duration)
    return abn_evt_mgt


def init_obsv_meta_coll_thd():
    obsv_meta_mgt = ObserveMetaMgt()
    metadata_consumer = init_metadata_consumer()
    obsv_meta_coll_thread = ObsvMetaCollThread(obsv_meta_mgt, metadata_consumer)
    obsv_meta_coll_thread.setDaemon(True)
    return obsv_meta_coll_thread


def send_cause_event(cause_producer: KafkaProducer, cause_msg):
    logger.logger.debug(json.dumps(cause_msg, indent=2))

    infer_kafka_conf = infer_config.kafka_conf.get('inference_topic')
    try:
        cause_producer.send(infer_kafka_conf.get('topic_id'), json.dumps(cause_msg).encode())
    except KafkaTimeoutError as ex:
        logger.logger.error(ex)
        return
    logger.logger.info('A cause inferring event has been sent to kafka.')


def main():
    if not init_config():
        return
    logger.logger.info('Start cause inference service...')

    cause_producer = init_cause_producer()
    abn_evt_mgt = init_abn_evt_mgt()

    obsv_meta_coll_thread = init_obsv_meta_coll_thd()
    obsv_meta_coll_thread.start()
    time.sleep(5)

    while True:
        logger.logger.info('Start consuming abnormal kpi event...')
        try:
            abn_kpi, abn_metrics = abn_evt_mgt.get_abnormal_info()
        except NoKpiEventException:
            time.sleep(ABN_KPI_POLL_INTERVAL_SEC)
            abn_evt_mgt.consume_kpi_evts()
            continue
        logger.logger.debug('Abnormal kpi is: {}'.format(abn_kpi))
        logger.logger.debug('Abnormal metrics are: {}'.format(abn_metrics))

        try:
            cause_res = cause_locating(abn_kpi, abn_metrics)
        except InferenceException as ie:
            logger.logger.warning(ie)
            continue
        if not cause_res:
            logger.logger.info('No cause detected, event_id={}'.format(abn_kpi.event_id))
            continue
        cause_msg = gen_cause_msg(abn_kpi, cause_res)
        send_cause_event(cause_producer, cause_msg)


if __name__ == '__main__':
    main()
