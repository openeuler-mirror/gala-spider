from typing import List

from cause_inference.cause_keyword import cause_keyword_mgt
from cause_inference.model import Cause, MetricNode, AbnormalEvent
from cause_inference.model import VirtualMetricCategory, virtual_metric_id_map, is_virtual_metric


def format_infer_result(causes: List[Cause]):
    abn_kpi = format_abn_kpi(causes[0].path[len(causes[0].path) - 1])
    cause_metrics = format_cause_metrics(causes)
    desc = format_desc_info(abn_kpi, cause_metrics)

    res = {
        'abnormal_kpi': abn_kpi,
        'cause_metrics': cause_metrics,
        'desc': desc
    }
    return res


def format_abn_kpi(abn_kpi_node: MetricNode):
    abn_kpi = {
        'metric_id': abn_kpi_node.node_id.metric_id,
        'entity_id': abn_kpi_node.node_attrs.get('entity_id'),
        'timestamp': abn_kpi_node.node_attrs.get('timestamp'),
        'metric_labels': abn_kpi_node.node_attrs.get('metric_labels'),
        'desc': abn_kpi_node.node_attrs.get('desc'),
    }
    return abn_kpi


def format_cause_metrics(causes: List[Cause]):
    cause_metrics = []
    for cause in causes:
        node_attrs = cause.path[0].node_attrs
        cause_metric = {
            'metric_id': cause.metric_id,
            'entity_id': cause.entity_id,
            'metric_labels': node_attrs.get('metric_labels', {}),
            'timestamp': node_attrs.get('timestamp'),
            'desc': node_attrs.get('desc'),
            'score': cause.cause_score,
            'keyword': cause_keyword_mgt.get_keyword_of_entity(node_attrs.get('entity_type')),
        }
        path = []
        for node in cause.path:
            node_attrs = node.node_attrs
            metric_id = node.node_id.metric_id
            if is_virtual_metric(metric_id):
                metric_id = virtual_metric_id_map.get(VirtualMetricCategory.DEFAULT.value)
            path.append({
                'metric_id': metric_id,
                'entity_id': node_attrs.get('entity_id'),
                'metric_labels': node_attrs.get('metric_labels', {}),
                'timestamp': node_attrs.get('timestamp'),
                'desc': node_attrs.get('desc'),
                'score': node_attrs.get('corr_score', 0.0),
            })
        cause_metric['path'] = path
        cause_metrics.append(cause_metric)
    return cause_metrics


def format_desc_info(abn_kpi, cause_metrics):
    desc = '{}，前 {} 个根因是：'.format(abn_kpi.get('desc'), len(cause_metrics))
    for i, cause_metric in enumerate(cause_metrics):
        desc += '{}. {}；'.format(i + 1, cause_metric.get('desc'))
    return desc


def gen_cause_msg(abn_kpi: AbnormalEvent, cause_res: dict) -> dict:
    cause_msg = {
        'Timestamp': abn_kpi.timestamp,
        'event_id': abn_kpi.event_id,
        'Attributes': {
            'event_id': abn_kpi.event_id
        },
        'Resource': cause_res,
        'keywords': gen_keywords(cause_res),
        'SeverityText': 'WARN',
        'SeverityNumber': 13,
        'Body': 'A cause inferring event for an abnormal event',
    }
    return cause_msg


def gen_keywords(cause_res: dict) -> list:
    keywords = []
    for cause_metric in cause_res.get('cause_metrics'):
        keywords.append(cause_metric.get('keyword'))
    return keywords
