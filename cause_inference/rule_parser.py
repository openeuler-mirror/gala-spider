import os
from abc import ABCMeta
from abc import abstractmethod
from typing import List, Dict, Tuple
from itertools import permutations

import yaml

from spider.util import logger
from spider.conf.observe_meta import EntityType, RelationType
from cause_inference.model import MetricCategoryDetail
from cause_inference.model import TopoNode, TopoEdge
from cause_inference.model import virtual_metric_id_map, is_virtual_category
from cause_inference.trend import parse_trend


METRIC_CATEGORY_ALL = 'ALL'
METRIC_CATEGORY_OTHER = 'OTHER'

QEMU_PROC_NAME = 'qemu-kvm'


class MetricCategoryPair:
    def __init__(self, from_: str, to_: str):
        self.from_ = from_
        self.to_ = to_


class RuleMeta:
    def __init__(self, from_type: str, to_type: str, from_categories: Dict[str, MetricCategoryDetail] = None,
                 to_categories: Dict[str, MetricCategoryDetail] = None, metric_range: List[MetricCategoryPair] = None):
        self.from_type = from_type
        self.to_type = to_type
        self.from_categories = from_categories or {}
        self.to_categories = to_categories or {}
        self.category_pairs: List[MetricCategoryPair] = metric_range or []

    @staticmethod
    def aggregate_metric_from_groups(category_type, metric_groups) -> List[dict]:
        res = []
        if category_type == METRIC_CATEGORY_ALL:
            for cate_type, metric_group in metric_groups.items():
                if is_virtual_category(cate_type):
                    continue
                elif cate_type == METRIC_CATEGORY_OTHER:
                    res.extend({'cate_type': cate_type, 'metrics': [metric]} for metric in metric_group)
                else:
                    res.append({'cate_type': cate_type, 'metrics': metric_group})
        else:
            metric_group = metric_groups.get(category_type)
            if metric_group:
                res.append({'cate_type': category_type, 'metrics': metric_group})

        return res

    @staticmethod
    def _group_metric_by_category(metrics: list, categories: Dict[str, MetricCategoryDetail]) -> Dict[str, list]:
        parts = {}
        parted_metrics = set()
        for cate_type, cate_detail in categories.items():
            part = []
            for metric in metrics:
                if metric in cate_detail.metrics:
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

        for virtual_cate_type, virtual_metric_id in virtual_metric_id_map.items():
            parts.setdefault(virtual_cate_type, [virtual_metric_id])

        return parts

    def get_avail_causal_relations(self, real_from_metrics: list, real_to_metrics: list) -> List[Tuple[dict, dict]]:
        """
        :return:
            example:
            [({'cate_type': 'PROC_IO_LOAD', 'trend': DataTrend.RISE, 'metrics': ['m1', 'm2']},
            {'cate_type': 'DISK_IO_LOAD', 'trend': DataTrend.RISE, 'metrics': ['m3', 'm4']})]
        """
        causal_relations = []

        from_groups = self._group_metric_by_category(real_from_metrics, self.from_categories)
        to_groups = self._group_metric_by_category(real_to_metrics, self.to_categories)
        for cate_pair in self.category_pairs:
            all_from_metrics = self.aggregate_metric_from_groups(cate_pair.from_, from_groups)
            all_to_metrics = self.aggregate_metric_from_groups(cate_pair.to_, to_groups)
            for from_metrics in all_from_metrics:
                for to_metrics in all_to_metrics:
                    causal_relations.append((from_metrics, to_metrics))

        self.add_trend_info(causal_relations)

        return causal_relations

    def add_trend_info(self, causal_relations: List[Tuple[dict, dict]]):
        for f_relation, t_relation in causal_relations:
            f_cate_detail = self.from_categories.get(f_relation.get('cate_type'))
            t_cate_detail = self.to_categories.get(t_relation.get('cate_type'))
            if f_cate_detail is not None:
                f_relation.setdefault('trend', f_cate_detail.trend)
            if t_cate_detail is not None:
                t_relation.setdefault('trend', t_cate_detail.trend)


def get_causal_relation(f_node: TopoNode, t_node: TopoNode) -> Tuple[str, str]:
    return f_node.id, t_node.id


class Rule(metaclass=ABCMeta):
    @abstractmethod
    def rule_parsing(self, topo_nodes: Dict[str, TopoNode], topo_edges: Dict[str, TopoEdge]) -> List[Tuple[str, str]]:
        pass


# 规则：如果一个 tcp_link 观测实例 A 和一个 sli 观测实例 B 属于同一个 process 观测实例 C，则建立 A 到 B 的因果关系。
class SliRule(Rule):
    def rule_parsing(self, topo_nodes: Dict[str, TopoNode], topo_edges: Dict[str, TopoEdge]) -> List[Tuple[str, str]]:
        causal_relations = []
        tcp_bt_p = []
        sli_bt_p = []
        for _, edge in topo_edges.items():
            if edge.type != RelationType.BELONGS_TO.value:
                continue

            f_node = topo_nodes.get(edge.from_id)
            t_node = topo_nodes.get(edge.to_id)
            if not f_node or not t_node:
                continue
            if t_node.entity_type != EntityType.PROCESS.value:
                continue

            if f_node.entity_type == EntityType.TCP_LINK.value:
                tcp_bt_p.append(edge)
            elif f_node.entity_type == EntityType.SLI.value:
                sli_bt_p.append(edge)

        for edge1 in tcp_bt_p:
            for edge2 in sli_bt_p:
                if edge1.to_id == edge2.to_id:
                    causal_relations.append(get_causal_relation(topo_nodes.get(edge1.from_id),
                                                                topo_nodes.get(edge2.from_id)))

        return causal_relations


class BelongsToRule(Rule):
    def rule_parsing(self, topo_nodes: Dict[str, TopoNode], topo_edges: Dict[str, TopoEdge]) -> List[Tuple[str, str]]:
        causal_relations = []
        for _, edge in topo_edges.items():
            if edge.type != RelationType.BELONGS_TO.value:
                continue
            f_node = topo_nodes.get(edge.from_id)
            t_node = topo_nodes.get(edge.to_id)
            if not f_node or not t_node:
                continue

            if f_node.entity_type == EntityType.SLI.value and t_node.entity_type == EntityType.PROCESS.value:
                # 规则：建立 process 到 sli 的因果关系
                causal_relations.append(get_causal_relation(t_node, f_node))
            elif f_node.entity_type == EntityType.BLOCK.value and t_node.entity_type == EntityType.DISK.value:
                # 规则：建立 disk 到 block 的因果关系
                causal_relations.append(get_causal_relation(t_node, f_node))
        return causal_relations


# 规则：如果观测实例 A 到观测实例 B 存在 runs_on 关系，则建立 B 到 A 的因果关系。
class RunsOnRule(Rule):
    def rule_parsing(self, topo_nodes: Dict[str, TopoNode], topo_edges: Dict[str, TopoEdge]) -> List[Tuple[str, str]]:
        causal_relations = []
        for _, edge in topo_edges.items():
            if edge.type != RelationType.RUNS_ON.value:
                continue
            f_node, t_node = topo_nodes.get(edge.from_id), topo_nodes.get(edge.to_id)
            if not f_node or not t_node:
                continue
            causal_relations.append(get_causal_relation(t_node, f_node))
        return causal_relations


class HostRule(Rule):
    @staticmethod
    def check_rule_type(f_node_type: str, t_node_type: str) -> bool:
        if (f_node_type, t_node_type) == (EntityType.PROCESS.value, EntityType.DISK.value):
            return True
        if (f_node_type, t_node_type) == (EntityType.BLOCK.value, EntityType.PROCESS.value):
            return True
        if (f_node_type, t_node_type) == (EntityType.CPU.value, EntityType.PROCESS.value):
            return True
        if (f_node_type, t_node_type) == (EntityType.NETCARD.value, EntityType.TCP_LINK.value):
            return True
        return False

    def rule_parsing(self, topo_nodes: Dict[str, TopoNode], topo_edges: Dict[str, TopoEdge]) -> List[Tuple[str, str]]:
        causal_relations = []

        host_nodes_map: Dict[str, List[TopoNode]] = {}
        for node in topo_nodes.values():
            val = host_nodes_map.setdefault(node.machine_id, [])
            val.append(node)

        for host_nodes in host_nodes_map.values():
            for f_node, t_node in permutations(host_nodes, 2):
                if not self.check_rule_type(f_node.entity_type, t_node.entity_type):
                    continue
                causal_relations.append(get_causal_relation(f_node, t_node))

        return causal_relations


class CrossHostRule(Rule):
    @staticmethod
    def parse_runs_on_rule(f_node: TopoNode, t_node: TopoNode, node_m_t_map: dict) -> List[Tuple[str, str]]:
        causal_relations = []
        if (f_node.entity_type, t_node.entity_type) != (EntityType.HOST.value, EntityType.PROCESS.value):
            return []

        f_disk_nodes = node_m_t_map.get((f_node.machine_id, EntityType.DISK.value), [])
        for node in f_disk_nodes:
            causal_relations.append(get_causal_relation(node, t_node))

        f_block_nodes = node_m_t_map.get((f_node.machine_id, EntityType.BLOCK.value), [])
        for node in f_block_nodes:
            causal_relations.append(get_causal_relation(t_node, node))

        return causal_relations

    @staticmethod
    def parse_store_in_rule(f_node: TopoNode, t_node: TopoNode, node_m_t_map: dict) -> List[Tuple[str, str]]:
        causal_relations = []
        if (f_node.entity_type, t_node.entity_type) != (EntityType.HOST.value, EntityType.HOST.value):
            return []

        f_proc_nodes = node_m_t_map.get((f_node.machine_id, EntityType.PROCESS.value), [])
        t_disk_nodes = node_m_t_map.get((t_node.machine_id, EntityType.DISK.value), [])
        t_block_nodes = node_m_t_map.get((t_node.machine_id, EntityType.BLOCK.value), [])
        for proc_node in f_proc_nodes:
            if proc_node.raw_data.get('comm') != QEMU_PROC_NAME:
                continue
            for disk_node in t_disk_nodes:
                causal_relations.append(get_causal_relation(proc_node, disk_node))
            for block_node in t_block_nodes:
                causal_relations.append(get_causal_relation(block_node, proc_node))

        return causal_relations

    def rule_parsing(self, topo_nodes: Dict[str, TopoNode], topo_edges: Dict[str, TopoEdge]) -> List[Tuple[str, str]]:
        causal_relations = []

        node_m_t_map = {}
        for node in topo_nodes.values():
            key = (node.machine_id, node.entity_type)
            val = node_m_t_map.setdefault(key, [])
            val.append(node)

        for edge in topo_edges.values():
            f_node = topo_nodes.get(edge.from_id)
            t_node = topo_nodes.get(edge.to_id)
            if not f_node or not t_node:
                continue
            if f_node.machine_id == t_node.machine_id:
                continue
            if edge.type == RelationType.RUNS_ON.value:
                causal_relations.extend(self.parse_runs_on_rule(f_node, t_node, node_m_t_map))
            if edge.type == RelationType.STORE_IN.value:
                causal_relations.extend(self.parse_store_in_rule(f_node, t_node, node_m_t_map))

        return causal_relations


class RuleEngine:
    def __init__(self):
        self.rules: List[Rule] = []
        self.cross_rules: List[Rule] = []
        self.metric_categories: Dict[str, Dict[str, MetricCategoryDetail]] = {}
        self.rule_metas: Dict[tuple, RuleMeta] = {}
        self.cross_rule_metas: Dict[tuple, RuleMeta] = {}

    def add_rule(self, rule: Rule):
        self.rules.append(rule)

    def add_cross_rule(self, rule: Rule):
        self.cross_rules.append(rule)

    def rule_parsing(self, topo_nodes: Dict[str, TopoNode], topo_edges: Dict[str, TopoEdge]) -> List[Tuple[str, str]]:
        causal_relations = []
        for rule in self.rules:
            causal_relations.extend(rule.rule_parsing(topo_nodes, topo_edges))
        return causal_relations

    def cross_rule_parsing(self, topo_nodes: Dict[str, TopoNode], topo_edges: Dict[str, TopoEdge])\
            -> List[Tuple[str, str]]:
        causal_relations = []
        for rule in self.cross_rules:
            causal_relations.extend(rule.rule_parsing(topo_nodes, topo_edges))
        return causal_relations

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
            from_type = entity_cause_graph.nodes[edge[0]].get('entity_type')
            from_machine_id = entity_cause_graph.nodes[edge[0]].get('machine_id')
            to_type = entity_cause_graph.nodes[edge[1]].get('entity_type')
            to_machine_id = entity_cause_graph.nodes[edge[1]].get('machine_id')
            if from_machine_id == to_machine_id:
                rule_meta = self.rule_metas.get((from_type, to_type))
            else:
                rule_meta = self.cross_rule_metas.get((from_type, to_type))
            if not rule_meta:
                rule_meta = self.create_default_rule_meta(from_type, to_type)
            entity_cause_graph.edges[edge]["rule_meta"] = rule_meta

    def load_rule_meta_from_dict(self, data: dict):
        self.load_metric_categories(data.get('metric_categories', {}))
        self.load_host_infer_rules(data.get("infer_rules", []))
        self.load_cross_infer_rules(data.get("cross_rules", []))

    def load_host_infer_rules(self, host_rules: list):
        self.rule_metas.update(self._load_infer_rules(host_rules))

    def load_cross_infer_rules(self, cross_rules: list):
        self.cross_rule_metas.update(self._load_infer_rules(cross_rules))

    def load_metric_categories(self, metric_categories: dict):
        for entity_type, categories in metric_categories.items():
            category_dict: Dict[str, MetricCategoryDetail] = {}
            for category in categories:
                cate_type = category.get('category')
                cate_detail = MetricCategoryDetail(cate_type, category.get('metrics'),
                                                   parse_trend(category.get('trend')))
                category_dict.setdefault(cate_type, cate_detail)
            self.metric_categories.setdefault(entity_type, category_dict)

    def _load_infer_rules(self, infer_rules: list) -> dict:
        rule_metas = {}
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
            rule_metas.setdefault((from_entity_type, to_entity_type), saved_rule_meta)
        return rule_metas


rule_engine = RuleEngine()
rule_engine.add_rule(BelongsToRule())
rule_engine.add_rule(RunsOnRule())
rule_engine.add_rule(SliRule())
rule_engine.add_rule(HostRule())
rule_engine.add_cross_rule(CrossHostRule())
