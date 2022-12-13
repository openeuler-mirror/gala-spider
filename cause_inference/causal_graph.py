from typing import List, Dict

import networkx as nx

from cause_inference.model import is_virtual_category, TopoNode, AbnormalEvent, MetricNodeId
from cause_inference.trend import check_trend
from spider.util import logger


class CausalGraph:
    def __init__(self):
        self.entity_cause_graph = nx.DiGraph()
        self.metric_cause_graph = nx.DiGraph()

    @staticmethod
    def is_virtual_metric_group(metric_group: dict) -> bool:
        return is_virtual_category(metric_group.get('cate_type'))

    def init_entity_cause_graph(self, entity_causal_relations: List[tuple], topo_nodes: Dict[str, TopoNode]):
        for causal_relation in entity_causal_relations:
            f_n_id, t_n_id = causal_relation[0], causal_relation[1]
            f_node, t_node = topo_nodes.get(f_n_id), topo_nodes.get(t_n_id)
            if not f_node or not t_node:
                continue

            if f_n_id not in self.entity_cause_graph:
                self.add_entity_node(f_node)
            if t_n_id not in self.entity_cause_graph:
                self.add_entity_node(t_node)

            self.entity_cause_graph.add_edge(f_n_id, t_n_id)

    def add_entity_node(self, node: TopoNode):
        self.entity_cause_graph.add_node(node.id, id=node.id, entity_id=node.entity_id, entity_type=node.entity_type,
                                         machine_id=node.machine_id, raw_data=node.raw_data)

    def add_abn_metrics(self, abn_metrics: List[AbnormalEvent]):
        entity_ids = {n_attrs.get('entity_id'): n_id for n_id, n_attrs in self.entity_cause_graph.nodes.items()}
        for abn_metric in abn_metrics:
            node_id = entity_ids.get(abn_metric.abnormal_entity_id)
            if not node_id:
                continue
            self.set_abnormal_status(node_id, True)
            self.add_abnormal_metric(node_id, abn_metric)

    def prune_by_abnormal_node(self):
        node_ids = list(self.entity_cause_graph.nodes)
        for node_id in node_ids:
            if not self.is_abnormal(node_id):
                self.entity_cause_graph.remove_node(node_id)

    def set_abnormal_status(self, node_id, abnormal_status):
        self.entity_cause_graph.nodes[node_id]['is_abnormal'] = abnormal_status

    def is_abnormal(self, node_id):
        if 'is_abnormal' not in self.entity_cause_graph.nodes[node_id]:
            return False
        return self.entity_cause_graph.nodes[node_id]['is_abnormal']

    def add_abnormal_metric(self, node_id, abn_metric: AbnormalEvent):
        node_attrs = self.entity_cause_graph.nodes[node_id]
        abn_metrics = node_attrs.setdefault('abnormal_metrics', {})
        if abn_metric.abnormal_metric_id in abn_metrics:
            # 去除（在不同时间点上）重复的异常metric
            if abn_metric.timestamp > abn_metrics.get(abn_metric.abnormal_metric_id).get('timestamp'):
                abn_metrics[abn_metric.abnormal_metric_id] = abn_metric.to_dict()
        else:
            abn_metrics[abn_metric.abnormal_metric_id] = abn_metric.to_dict()

    def get_abnormal_metrics(self, node_id) -> dict:
        return self.entity_cause_graph.nodes[node_id].get('abnormal_metrics', {})

    def filter_abn_metrics_by_corr_score(self):
        for n_id in self.entity_cause_graph.nodes:
            abn_metrics = self.get_abnormal_metrics(n_id)
            metric_ids = list(abn_metrics.keys())
            for metric_id in metric_ids:
                corr_score = abn_metrics.get(metric_id).get('corr_score', 0)
                if corr_score < 0.1:
                    del abn_metrics[metric_id]
            if len(abn_metrics) == 0:
                self.set_abnormal_status(n_id, False)

    def init_metric_cause_graph(self):
        for entity_n_id in self.entity_cause_graph.nodes:
            entity_type = self.entity_cause_graph.nodes[entity_n_id].get('entity_type')
            for abn_m_id, abn_m_attrs in self.get_abnormal_metrics(entity_n_id).items():
                m_node_id = MetricNodeId(entity_n_id, abn_m_id)
                m_node_attrs = {'entity_type': entity_type}
                m_node_attrs.update(abn_m_attrs)
                self.metric_cause_graph.add_node(m_node_id, **m_node_attrs)
        for edge in self.entity_cause_graph.edges:
            self.init_metric_edge(edge)

    def init_metric_edge(self, entity_edge):
        f_entity_n_id = entity_edge[0]
        t_entity_n_id = entity_edge[1]
        avail_relations = self.get_avail_metric_causal_relations(entity_edge)

        unique = set()
        for f_metric_group, t_metric_group in avail_relations:
            if self.is_virtual_metric_group(f_metric_group):
                self.add_virtual_metric_node(f_entity_n_id, f_metric_group.get('metrics')[0])
            if self.is_virtual_metric_group(t_metric_group):
                self.add_virtual_metric_node(t_entity_n_id, t_metric_group.get('metrics')[0])

            self.filter_metric_group_by_trend(f_metric_group, f_entity_n_id)
            self.filter_metric_group_by_trend(t_metric_group, t_entity_n_id)
            if len(f_metric_group.get('metrics')) == 0 or len(t_metric_group.get('metrics')) == 0:
                continue

            f_metric_id = self.metric_with_largest_score(f_metric_group.get('metrics'), f_entity_n_id)
            t_metric_id = self.metric_with_largest_score(t_metric_group.get('metrics'), t_entity_n_id)
            if (f_metric_id, t_metric_id) not in unique:
                f_m_node_id = MetricNodeId(f_entity_n_id, f_metric_id)
                t_m_node_id = MetricNodeId(t_entity_n_id, t_metric_id)
                self.metric_cause_graph.add_edge(f_m_node_id, t_m_node_id)
                self.metric_cause_graph.nodes[f_m_node_id].setdefault('trend', f_metric_group.get('trend'))
                self.metric_cause_graph.nodes[t_m_node_id].setdefault('trend', t_metric_group.get('trend'))
                unique.add((f_metric_id, t_metric_id))

    def add_virtual_metric_node(self, entity_n_id, metric_id):
        entity_n_attrs = self.entity_cause_graph.nodes[entity_n_id]
        metric_n_id = MetricNodeId(entity_n_id, metric_id)
        metric_n_attrs = {
            'entity_id': entity_n_attrs.get('entity_id'),
            'entity_type': entity_n_attrs.get('entity_type'),
            'machine_id': entity_n_attrs.get('machine_id')
        }
        self.metric_cause_graph.add_node(metric_n_id, **metric_n_attrs)

    def get_avail_metric_causal_relations(self, entity_edge):
        f_metric_ids = self.get_abn_metric_ids(entity_edge[0])
        t_metric_ids = self.get_abn_metric_ids(entity_edge[1])
        rule_meta = self.entity_cause_graph.edges[entity_edge].get('rule_meta')
        return rule_meta.get_avail_causal_relations(f_metric_ids, t_metric_ids)

    def get_abn_metric_ids(self, entity_n_id):
        abn_metrics = self.get_abnormal_metrics(entity_n_id)
        return list(abn_metrics.keys())

    def metric_with_largest_score(self, metric_ids: list, entity_n_id) -> str:
        if len(metric_ids) == 1:
            return metric_ids[0]

        abn_metrics = self.get_abnormal_metrics(entity_n_id)

        metric_id_of_largest = metric_ids[0]
        largest_abn_score = abn_metrics.get(metric_id_of_largest).get('corr_score')
        for metric_id in metric_ids:
            abn_score = abn_metrics.get(metric_id).get('corr_score')
            if abn_score > largest_abn_score:
                metric_id_of_largest = metric_id
                largest_abn_score = abn_score

        return metric_id_of_largest

    def filter_metric_group_by_trend(self, metric_group: dict, entity_n_id):
        if self.is_virtual_metric_group(metric_group):
            return

        abn_metrics = self.get_abnormal_metrics(entity_n_id)
        metrics = metric_group.get('metrics')

        filtered_metrics = []
        for metric_id in metrics:
            if check_trend(metric_group.get('trend'), abn_metrics.get(metric_id, {}).get('real_trend')):
                filtered_metrics.append(metric_id)
            else:
                logger.logger.debug('Trend of the metric({},{}) not meet the expect.'.format(metric_id, entity_n_id))

        metric_group['metrics'] = filtered_metrics
