import os
from abc import ABCMeta
from abc import abstractmethod
from typing import List

import yaml

from spider.conf.observe_meta import RelationType
from spider.conf.observe_meta import EntityType
from spider.util import logger


class MetricPairSet:
    def __init__(self, from_: set, to_: set):
        self.from_ = from_
        self.to_ = to_

    def check_metric_pair(self, from_metric_id: str, to_metric_id: str) -> bool:
        if self.from_ and from_metric_id not in self.from_:
            return False
        if self.to_ and to_metric_id not in self.to_:
            return False
        return True


class RuleMeta:
    def __init__(self, from_type, to_type, metric_range=None):
        self.from_type = from_type
        self.to_type = to_type
        self.metric_range: List[MetricPairSet] = metric_range or []

    def check_metric_pair(self, from_metric_id: str, to_metric_id: str) -> bool:
        if not self.metric_range:
            return True
        for item in self.metric_range:
            if item.check_metric_pair(from_metric_id, to_metric_id):
                return True
        return False


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
        self.rule_metas = {}

    def add_rule(self, rule: Rule):
        self.rules.append(rule)

    def rule_parsing(self, causal_graph):
        for rule in self.rules:
            rule.rule_parsing(causal_graph)

    def load_rule_meta_from_yaml(self, rule_path: str) -> bool:
        abs_rule_path = os.path.abspath(rule_path)
        if not os.path.exists(abs_rule_path):
            logger.logger.warning("Rule meta path '{}' not exist", abs_rule_path)
            return True
        try:
            with open(abs_rule_path, 'r') as file:
                data = yaml.safe_load(file)
        except IOError as ex:
            logger.logger.warning(ex)
            return False

        infer_rules = data.get("infer_rules", [])
        for rule_meta in infer_rules:
            saved_metric_range = []
            for item in rule_meta.get("metric_range", []):
                saved_metric_range.append(MetricPairSet(set(item.get('from', [])), set(item.get('to', []))))
            saved_rule_meta = RuleMeta(rule_meta.get('from_type'), rule_meta.get('to_type'), saved_metric_range)
            self.rule_metas.setdefault((rule_meta.get("from_type"), rule_meta.get("to_type")), saved_rule_meta)

        return True

    def add_rule_meta(self, causal_graph):
        entity_cause_graph = causal_graph.entity_cause_graph
        for edge in entity_cause_graph.edges:
            from_type = entity_cause_graph.nodes[edge[0]].get('type')
            to_type = entity_cause_graph.nodes[edge[1]].get('type')
            entity_cause_graph.edges[edge]["rule_meta"] = self.rule_metas.get((from_type, to_type))


rule_engine = RuleEngine()
rule_engine.add_rule(BelongsToRule1())
rule_engine.add_rule(RunsOnRule1())
rule_engine.add_rule(SliRule1())
rule_engine.add_rule(ProcessRule1())
rule_engine.add_rule(CpuRule1())
rule_engine.add_rule(NicRule1())
