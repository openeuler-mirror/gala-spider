import os
from abc import ABCMeta
from abc import abstractmethod
from typing import List, Dict, Tuple

import yaml

from spider.conf.observe_meta import RelationType
from spider.conf.observe_meta import EntityType
from spider.util import logger

METRIC_CATEGORY_ALL = 'ALL'
METRIC_CATEGORY_OTHER = 'OTHER'
METRIC_CATEGORY_VIRTUAL = 'VIRTUAL'
METRIC_ID_OF_CATEGORY_VIRTUAL = 'virtual_metric'


def is_virtual_metric(metric_id: str) -> bool:
    return metric_id == METRIC_ID_OF_CATEGORY_VIRTUAL


class MetricCategoryPair:
    def __init__(self, from_: str, to_: str):
        self.from_ = from_
        self.to_ = to_


class RuleMeta:
    def __init__(self, from_type, to_type, from_categories=None, to_categories=None, metric_range=None):
        self.from_type = from_type
        self.to_type = to_type
        self.from_categories = from_categories or {}
        self.to_categories = to_categories or {}
        self.category_pairs: List[MetricCategoryPair] = metric_range or []

    @staticmethod
    def aggregate_metric_from_groups(category_type, metric_groups) -> List[list]:
        res = []
        if category_type == METRIC_CATEGORY_ALL:
            for cate_type, metric_group in metric_groups.items():
                if cate_type == METRIC_CATEGORY_VIRTUAL:
                    continue
                elif cate_type == METRIC_CATEGORY_OTHER:
                    res.extend([metric] for metric in metric_group)
                else:
                    res.append(metric_group)
        else:
            metric_group = metric_groups.get(category_type)
            if metric_group:
                res.append(metric_group)

        return res

    @staticmethod
    def _group_metric_by_category(metrics, categories) -> Dict[str, list]:
        parts = {}
        parted_metrics = set()
        for cate_type, cate_metrics in categories.items():
            part = []
            for metric in metrics:
                if metric in cate_metrics:
                    part.append(metric)
                    parted_metrics.add(metric)
            if len(part) > 0:
                parts.setdefault(cate_type, part)

        other_part = []
        for metric in metrics:
            if metric not in parted_metrics:
                other_part.append(metric)
        if len(other_part) > 0:
            parts.setdefault(METRIC_CATEGORY_OTHER, other_part)

        virtual_part = [METRIC_ID_OF_CATEGORY_VIRTUAL]
        parts.setdefault(METRIC_CATEGORY_VIRTUAL, virtual_part)

        return parts

    def get_avail_causal_relations(self, real_from_metrics, real_to_metrics) -> List[Tuple[list, list]]:
        causal_relations = []

        from_groups = self._group_metric_by_category(real_from_metrics, self.from_categories)
        to_groups = self._group_metric_by_category(real_to_metrics, self.to_categories)
        for cate_pair in self.category_pairs:
            all_from_metrics = self.aggregate_metric_from_groups(cate_pair.from_, from_groups)
            all_to_metrics = self.aggregate_metric_from_groups(cate_pair.to_, to_groups)
            for from_metrics in all_from_metrics:
                for to_metrics in all_to_metrics:
                    causal_relations.append((from_metrics, to_metrics))

        return causal_relations


class Rule(metaclass=ABCMeta):
    @abstractmethod
    def rule_parsing(self, causal_graph):
        pass


# 规则：如果一个 tcp_link 观测实例 A 和一个 sli 观测实例 B 属于同一个 process 观测实例 C，则建立 A 到 B 的因果关系。
class SliRule1(Rule):
    def rule_parsing(self, causal_graph):
        topo_edges = causal_graph.topo_edges
        topo_nodes = causal_graph.topo_nodes

        tcp_bt_p = []
        sli_bt_p = []
        for _, edge in topo_edges.items():
            if edge.get('type') != RelationType.BELONGS_TO.value:
                continue
            from_n = topo_nodes.get(edge.get('_from'))
            to_n = topo_nodes.get(edge.get('_to'))
            if to_n.get('type') != EntityType.PROCESS.value:
                continue
            if from_n.get('type') == EntityType.TCP_LINK.value:
                tcp_bt_p.append(edge)
            elif from_n.get('type') == EntityType.SLI.value:
                sli_bt_p.append(edge)

        for edge1 in tcp_bt_p:
            for edge2 in sli_bt_p:
                if edge1.get('_to') == edge2.get('_to'):
                    causal_graph.entity_cause_graph.add_edge(edge1.get('_from'), edge2.get('_from'))


# 规则：如果观测实例 A 到观测实例 B 存在 belongs_to 关系，则建立 A 到 B 的因果关系。
class BelongsToRule1(Rule):
    def rule_parsing(self, causal_graph):
        topo_edges = causal_graph.topo_edges
        topo_nodes = causal_graph.topo_nodes
        entity_cause_graph = causal_graph.entity_cause_graph
        for _, edge in topo_edges.items():
            if edge.get('type') != RelationType.BELONGS_TO.value:
                continue
            from_node = topo_nodes.get(edge.get('_from'))
            to_node = topo_nodes.get(edge.get('_to'))
            from_type = from_node.get('type')
            to_type = to_node.get('type')

            if from_type == EntityType.SLI.value and to_type == EntityType.PROCESS.value:
                # 规则：建立 process 到 sli 的因果关系
                entity_cause_graph.add_edge(edge.get('_to'), edge.get('_from'), **edge)
            elif from_type == EntityType.BLOCK.value and to_type == EntityType.DISK.value:
                # 规则：建立 disk 到 block 的因果关系
                entity_cause_graph.add_edge(edge.get('_to'), edge.get('_from'), **edge)
            else:
                entity_cause_graph.add_edge(edge.get('_from'), edge.get('_to'), **edge)


# 规则：如果观测实例 A 到观测实例 B 存在 runs_on 关系，则建立 B 到 A 的因果关系。
class RunsOnRule1(Rule):
    def rule_parsing(self, causal_graph):
        topo_edges = causal_graph.topo_edges
        entity_cause_graph = causal_graph.entity_cause_graph
        for _, edge in topo_edges.items():
            if edge.get('type') != RelationType.RUNS_ON.value:
                continue
            entity_cause_graph.add_edge(edge.get('_to'), edge.get('_from'), **edge)


class ProcessRule1(Rule):
    def rule_parsing(self, causal_graph):
        topo_nodes = causal_graph.topo_nodes
        entity_cause_graph = causal_graph.entity_cause_graph

        proc_nodes = []
        disk_nodes = []
        block_nodes = []
        for node in topo_nodes.values():
            type_ = node.get('type')
            if type_ == EntityType.PROCESS.value:
                proc_nodes.append(node)
            elif type_ == EntityType.DISK.value:
                disk_nodes.append(node)
            elif type_ == EntityType.BLOCK.value:
                block_nodes.append(node)
        # 规则：如果 disk 和 process 属于同一个主机，则建立 process 到 disk 的因果关系
        for disk_node in disk_nodes:
            for proc_node in proc_nodes:
                if disk_node.get('machine_id') != proc_node.get('machine_id'):
                    continue
                entity_cause_graph.add_edge(proc_node.get('_id'), disk_node.get('_id'))
        # 规则：如果 block 和 process 属于同一个主机，则建立 block 到 process 的因果关系
        for blk_node in block_nodes:
            for proc_node in proc_nodes:
                if blk_node.get('machine_id') != proc_node.get('machine_id'):
                    continue
                entity_cause_graph.add_edge(blk_node.get('_id'), proc_node.get('_id'))


class CpuRule1(Rule):
    def rule_parsing(self, causal_graph):
        topo_nodes = causal_graph.topo_nodes
        entity_cause_graph = causal_graph.entity_cause_graph

        proc_nodes = []
        cpu_nodes = []
        for node in topo_nodes.values():
            type_ = node.get('type')
            if type_ == EntityType.PROCESS.value:
                proc_nodes.append(node)
            elif type_ == EntityType.CPU.value:
                cpu_nodes.append(node)
        # 规则：如果 cpu 和 process 属于同一个主机，则建立 cpu 到 process 的因果关系
        for cpu_node in cpu_nodes:
            for proc_node in proc_nodes:
                if cpu_node.get('machine_id') != proc_node.get('machine_id'):
                    continue
                entity_cause_graph.add_edge(cpu_node.get('_id'), proc_node.get('_id'))


class NicRule1(Rule):
    def rule_parsing(self, causal_graph):
        topo_nodes = causal_graph.topo_nodes
        entity_cause_graph = causal_graph.entity_cause_graph

        tcp_link_nodes = []
        nic_nodes = []
        for node in topo_nodes.values():
            type_ = node.get('type')
            if type_ == EntityType.TCP_LINK.value:
                tcp_link_nodes.append(node)
            elif type_ == EntityType.NETCARD.value:
                nic_nodes.append(node)
        # 规则：如果 nic 和 tcp_link 属于同一个主机，则建立 nic 到 tcp_link 的因果关系
        for nic_node in nic_nodes:
            for tcp_link_node in tcp_link_nodes:
                if nic_node.get('machine_id') != tcp_link_node.get('machine_id'):
                    continue
                entity_cause_graph.add_edge(nic_node.get('_id'), tcp_link_node.get('_id'))


class RuleEngine:
    def __init__(self):
        self.rules: List[Rule] = []
        self.metric_categories = {}
        self.rule_metas: Dict[tuple, RuleMeta] = {}

    def add_rule(self, rule: Rule):
        self.rules.append(rule)

    def rule_parsing(self, causal_graph):
        for rule in self.rules:
            rule.rule_parsing(causal_graph)

    def load_rule_meta_from_yaml(self, rule_path: str) -> bool:
        try:
            with open(os.path.abspath(rule_path), 'r') as file:
                data = yaml.safe_load(file)
        except IOError as ex:
            logger.logger.warning(ex)
            return False

        self.load_rule_meta_from_dict(data)
        return True

    def create_default_rule_meta(self, from_type, to_type):
        return RuleMeta(
            from_type,
            to_type,
            self.metric_categories.get(from_type),
            self.metric_categories.get(to_type),
            [MetricCategoryPair(METRIC_CATEGORY_ALL, METRIC_CATEGORY_ALL)]
        )

    def add_rule_meta(self, causal_graph):
        entity_cause_graph = causal_graph.entity_cause_graph
        for edge in entity_cause_graph.edges:
            from_type = entity_cause_graph.nodes[edge[0]].get('type')
            to_type = entity_cause_graph.nodes[edge[1]].get('type')
            rule_meta = self.rule_metas.get((from_type, to_type))
            if not rule_meta:
                rule_meta = self.create_default_rule_meta(from_type, to_type)
            entity_cause_graph.edges[edge]["rule_meta"] = rule_meta

    def load_rule_meta_from_dict(self, data: dict):
        self.load_metric_categories(data.get('metric_categories', {}))
        self.load_infer_rules(data.get("infer_rules", []))

    def load_metric_categories(self, metric_categories: dict):
        for entity_type, categories in metric_categories.items():
            category_dict = {}
            for category in categories:
                category_dict.setdefault(category.get('category'), category.get('metrics'))
            self.metric_categories.setdefault(entity_type, category_dict)

    def load_infer_rules(self, infer_rules: list):
        for rule_meta in infer_rules:
            from_entity_type = rule_meta.get('from_type')
            to_entity_type = rule_meta.get('to_type')
            saved_metric_range = []
            for item in rule_meta.get("metric_range", []):
                from_category = item.get('from')
                to_category = item.get('to')
                saved_metric_range.append(MetricCategoryPair(from_category, to_category))
            saved_rule_meta = RuleMeta(from_entity_type, to_entity_type, self.metric_categories.get(from_entity_type),
                                       self.metric_categories.get(to_entity_type), saved_metric_range)
            self.rule_metas.setdefault((from_entity_type, to_entity_type), saved_rule_meta)


rule_engine = RuleEngine()
rule_engine.add_rule(BelongsToRule1())
rule_engine.add_rule(RunsOnRule1())
rule_engine.add_rule(SliRule1())
rule_engine.add_rule(ProcessRule1())
rule_engine.add_rule(CpuRule1())
rule_engine.add_rule(NicRule1())
