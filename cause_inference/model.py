from typing import List

import networkx as nx

from spider.exceptions import MetadataException
from spider.conf.observe_meta import ObserveMetaMgt
from spider.util import logger
from spider.util.entity import concate_entity_id
from spider.util.entity import escape_entity_id
from cause_inference import rule_parser


class AbnormalEvent:
    def __init__(self, timestamp, abnormal_metric_id, abnormal_score=0.0,
                 metric_labels=None, abnormal_entity_id=None, desc=None):
        self.timestamp = timestamp
        self.abnormal_metric_id = abnormal_metric_id
        self.abnormal_score = abnormal_score
        self.metric_labels = metric_labels or {}
        self.abnormal_entity_id = abnormal_entity_id or ''
        self.desc = desc or ''
        self.hist_data = []

    def __repr__(self):
        return ('AbnormalEvent(timestamp={}, abnormal_metric_id="{}", abnormal_score={}, metric_labels={},'
                ' abnormal_entity_id={}, desc={})').format(
            self.timestamp,
            self.abnormal_metric_id,
            self.abnormal_score,
            self.metric_labels,
            self.abnormal_entity_id,
            self.desc
        )

    def set_hist_data(self, hist_data):
        self.hist_data = hist_data[:]

    def update_entity_id(self, obsv_meta_mgt: ObserveMetaMgt) -> bool:
        if self.abnormal_entity_id:
            return True

        try:
            entity_type = obsv_meta_mgt.get_entity_type_of_metric(self.abnormal_metric_id)
        except MetadataException as ex:
            logger.logger.debug(ex)
            return False

        obsv_meta = obsv_meta_mgt.get_observe_meta(entity_type)
        if not obsv_meta:
            return False
        self.abnormal_entity_id = escape_entity_id(concate_entity_id(entity_type, self.metric_labels, obsv_meta.keys))
        if not self.abnormal_entity_id:
            return False

        return True

    def to_dict(self):
        res = {
            'metric_id': self.abnormal_metric_id,
            'timestamp': self.timestamp,
            'abnormal_score': self.abnormal_score,
            'metric_labels': self.metric_labels,
            'entity_id': self.abnormal_entity_id,
            'desc': self.desc,
        }
        return res


class CausalGraph:
    def __init__(self, raw_topo_graph, abnormal_kpi: AbnormalEvent, abnormal_metrics: List[AbnormalEvent]):
        self.topo_nodes = raw_topo_graph.get('vertices', {})
        self.topo_edges = raw_topo_graph.get('edges', {})
        self.abnormal_kpi: AbnormalEvent = abnormal_kpi
        self.abnormal_metrics: List[AbnormalEvent] = abnormal_metrics

        self.entity_id_of_abn_kpi = None
        self.entity_cause_graph = nx.DiGraph()
        self.metric_cause_graph = nx.DiGraph()
        self.init_casual_graph()

    @staticmethod
    def is_virtual_metric_group(metric_group) -> bool:
        return len(metric_group) == 1 and rule_parser.is_virtual_metric(metric_group[0])

    def init_casual_graph(self):
        for node_id, node_attrs in self.topo_nodes.items():
            self.entity_cause_graph.add_node(node_id, **node_attrs)
            self.set_abnormal_status_of_node(node_id, False)

        # 标记有异常指标的节点
        abnormal_metrics = [self.abnormal_kpi]
        abnormal_metrics.extend(self.abnormal_metrics)
        for abn_metric in abnormal_metrics:
            for node_id, node_attrs in self.entity_cause_graph.nodes.items():
                if node_attrs.get('_key') != abn_metric.abnormal_entity_id:
                    continue
                if abn_metric.abnormal_metric_id == self.abnormal_kpi.abnormal_metric_id:
                    self.entity_id_of_abn_kpi = node_id
                self.set_abnormal_status_of_node(node_id, True)
                self.append_abnormal_metric_to_node(node_id, abn_metric)
                break

    def prune_by_abnormal_node(self):
        node_ids = list(self.entity_cause_graph.nodes)
        for node_id in node_ids:
            if not self.is_abnormal_of_node(node_id):
                self.entity_cause_graph.remove_node(node_id)

    def set_abnormal_status_of_node(self, node_id, abnormal_status):
        self.entity_cause_graph.nodes[node_id]['is_abnormal'] = abnormal_status

    def is_abnormal_of_node(self, node_id):
        if 'is_abnormal' not in self.entity_cause_graph.nodes[node_id]:
            return False
        return self.entity_cause_graph.nodes[node_id]['is_abnormal']

    def append_abnormal_metric_to_node(self, node_id, abn_metric):
        node_attrs = self.entity_cause_graph.nodes[node_id]
        abn_metrics = node_attrs.setdefault('abnormal_metrics', [])
        # 去除（在不同时间点上）重复的异常metric
        for i, metric in enumerate(abn_metrics):
            if metric.abnormal_metric_id == abn_metric.abnormal_metric_id:
                if abn_metric.timestamp > metric.timestamp:
                    abn_metrics[i] = abn_metric
                return
        abn_metrics.append(abn_metric)

    def get_abnormal_metrics_of_node(self, node_id):
        return self.entity_cause_graph.nodes[node_id].get('abnormal_metrics', [])

    def get_abnormal_metric_of_node(self, node_id, idx):
        return self.entity_cause_graph.nodes[node_id].get('abnormal_metrics')[idx]

    def init_metric_cause_graph(self):
        for entity_id in self.entity_cause_graph.nodes:
            for metric_evt in self.get_abnormal_metrics_of_node(entity_id):
                self.metric_cause_graph.add_node((entity_id, metric_evt.abnormal_metric_id), **metric_evt.to_dict())
        for edge in self.entity_cause_graph.edges:
            self.init_metric_edge(edge)

    def init_metric_edge(self, entity_edge):
        f_entity_id = entity_edge[0]
        t_entity_id = entity_edge[1]
        avail_relations = self.get_avail_metric_causal_relations(entity_edge)

        unique = set()
        for f_metric_group, t_metric_group in avail_relations:
            if self.is_virtual_metric_group(f_metric_group):
                self.add_virtual_metric_node(f_entity_id, f_metric_group[0])
            if self.is_virtual_metric_group(t_metric_group):
                self.add_virtual_metric_node(t_entity_id, t_metric_group[0])

            f_metric_id = self.metric_with_largest_abn_score(f_metric_group, f_entity_id)
            t_metric_id = self.metric_with_largest_abn_score(t_metric_group, t_entity_id)
            if (f_metric_id, t_metric_id) not in unique:
                self.metric_cause_graph.add_edge((f_entity_id, f_metric_id), (t_entity_id, t_metric_id))
                unique.add((f_metric_id, t_metric_id))

    def add_virtual_metric_node(self, entity_id, metric_id):
        self.metric_cause_graph.add_node((entity_id, metric_id))

    def get_avail_metric_causal_relations(self, entity_edge):
        f_metric_ids = self.get_abn_metric_ids(entity_edge[0])
        t_metric_ids = self.get_abn_metric_ids(entity_edge[1])
        rule_meta = self.entity_cause_graph.edges[entity_edge].get('rule_meta')
        return rule_meta.get_avail_causal_relations(f_metric_ids, t_metric_ids)

    def get_abn_metric_ids(self, entity_id):
        metric_evts = self.get_abnormal_metrics_of_node(entity_id)
        return [evt.abnormal_metric_id for evt in metric_evts]

    def metric_with_largest_abn_score(self, metric_group: list, entity_id) -> str:
        if len(metric_group) == 1:
            return metric_group[0]

        metric_evt_map = {}
        metric_evts = self.get_abnormal_metrics_of_node(entity_id)
        for metric_evt in metric_evts:
            metric_evt_map.setdefault(metric_evt.abnormal_metric_id, metric_evt)

        metric_id_of_largest = metric_group[0]
        largest_abn_score = metric_evt_map.get(metric_id_of_largest).abnormal_score
        for metric_id in metric_group:
            abn_score = metric_evt_map.get(metric_id).abnormal_score
            if abn_score > largest_abn_score:
                metric_id_of_largest = metric_id
                largest_abn_score = abn_score

        return metric_id_of_largest


class Cause:
    def __init__(self, metric_id, entity_id, cause_score, path=None):
        self.metric_id = metric_id
        self.entity_id = entity_id
        self.cause_score = cause_score
        self.path = path or []

    def to_dict(self):
        res = {
            'metric_id': self.metric_id,
            'entity_id': self.entity_id,
            'cause_score': self.cause_score
        }
        return res
