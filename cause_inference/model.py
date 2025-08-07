from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict

import networkx as nx

from spider.exceptions import MetadataException
from spider.conf.observe_meta import ObserveMetaMgt
from spider.util import logger
from spider.util.entity import concate_entity_id
from spider.util.entity import escape_entity_id


class VirtualMetricCategory(Enum):
    DEFAULT = 'VIRTUAL'
    IO_DELAY = 'VIRTUAL_IO_DELAY'
    IO_LOAD = 'VIRTUAL_IO_LOAD'
    NET_DELAY = 'VIRTUAL_NET_DELAY'


virtual_metric_id_map = {
    VirtualMetricCategory.DEFAULT.value: 'virtual_metric',
    VirtualMetricCategory.IO_DELAY.value: 'virtual_io_delay',
    VirtualMetricCategory.IO_LOAD.value: 'virtual_io_load',
    VirtualMetricCategory.NET_DELAY.value: 'virtual_net_delay'
}


def is_virtual_category(cate_type: str) -> bool:
    for v in VirtualMetricCategory.__members__.values():
        if v.value == cate_type:
            return True
    return False


def is_virtual_metric(metric_id: str) -> bool:
    for virtual_metric_id in virtual_metric_id_map.values():
        if metric_id == virtual_metric_id:
            return True
    return False


class AnomalyTrend(Enum):
    DEFAULT = 0
    RISE = 1
    FALL = 2


@dataclass
class MetricCategoryDetail:
    category: str
    metrics: List[str]
    trend: AnomalyTrend


@dataclass
class TopoNode:
    id: str
    entity_id: str
    entity_type: str
    machine_id: str
    timestamp: int
    raw_data: dict = field(default_factory=dict)


@dataclass
class TopoEdge:
    id: str
    type: str
    from_id: str
    to_id: str
    from_node: TopoNode = None
    to_node: TopoNode = None


@dataclass
class HostTopo:
    machine_id: str
    nodes: Dict[str, TopoNode]
    edges: Dict[str, TopoEdge]


@dataclass(frozen=True)
class MetricNodeId:
    entity_n_id: str
    metric_id: str


@dataclass
class MetricNode:
    node_id: MetricNodeId
    node_attrs: dict = field(default_factory=dict)


class AbnormalEvent:
    def __init__(self, timestamp, abnormal_metric_id, abnormal_score=0.0,
                 metric_labels=None, abnormal_entity_id=None, desc=None, event_id=None):
        self.timestamp = timestamp
        self.abnormal_metric_id = abnormal_metric_id
        self.abnormal_score = abnormal_score
        self.metric_labels = metric_labels or {}
        self.abnormal_entity_id = abnormal_entity_id or ''
        self.desc = desc or ''
        self.event_id = event_id or ''
        self.hist_data = []

    def __repr__(self):
        return 'AbnormalEvent(metric_id={}, entity_id={}, abnormal_score={}, timestamp={})'.format(
            self.abnormal_metric_id,
            self.abnormal_entity_id,
            self.abnormal_score,
            self.timestamp,
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
            'entity_id': self.abnormal_entity_id,
            'metric_labels': self.metric_labels,
            'timestamp': self.timestamp,
            'abnormal_score': self.abnormal_score,
            'desc': self.desc,
        }
        return res


class Cause:
    def __init__(self, metric_id, entity_id, cause_score, path: List[MetricNode] = None):
        self.metric_id = metric_id
        self.entity_id = entity_id
        self.cause_score = cause_score
        self.path: List[MetricNode] = path or []

    def to_dict(self):
        res = {
            'metric_id': self.metric_id,
            'entity_id': self.entity_id,
            'cause_score': self.cause_score
        }
        return res


class CauseTNode:
    def __init__(self, data: MetricNode = None):
        self.data = data
        self.childs: Dict[MetricNodeId, CauseTNode] = {}

    def add_child(self, node_id: MetricNodeId, tnode):
        self.childs.setdefault(node_id, tnode)


class CauseTree:
    def __init__(self, root_node: CauseTNode = None):
        self.root_node = root_node
        self.all_node_map: Dict[MetricNodeId, CauseTNode] = {}

    def append_all_causes(self, causes: List[Cause]) -> List[MetricNode]:
        newly_cause_nodes = []
        for cause in causes:
            newly_cause_nodes.extend(self.append_cause(cause))
        return newly_cause_nodes

    def append_cause(self, cause: Cause) -> List[MetricNode]:
        newly_cause_nodes = []
        path = cause.path
        tgt_node = path[len(path) - 1]
        if not self.root_node:
            self.root_node = CauseTNode(tgt_node)
            self.all_node_map.setdefault(tgt_node.node_id, self.root_node)
            newly_cause_nodes.append(tgt_node)
        mounted_tnode = self.all_node_map.get(tgt_node.node_id)
        if not mounted_tnode:
            return []

        pre_tnode = mounted_tnode
        idx = len(path) - 2
        while idx >= 0:
            cur_node = path[idx]
            cur_tnode = self.all_node_map.get(cur_node.node_id)
            if not cur_tnode:
                cur_tnode = CauseTNode(cur_node)
                self.all_node_map.setdefault(cur_node.node_id, cur_tnode)
                newly_cause_nodes.append(cur_node)
            pre_tnode.add_child(cur_node.node_id, cur_tnode)
            pre_tnode = cur_tnode
            idx -= 1

        return newly_cause_nodes

    def to_cause_graph(self) -> nx.DiGraph:
        cause_graph = nx.DiGraph()
        for node_id, tnode in self.all_node_map.items():
            cause_graph.add_node(node_id, **tnode.data.node_attrs)
        for node_id, tnode in self.all_node_map.items():
            for child_node_id in tnode.childs:
                cause_graph.add_edge(child_node_id, node_id)
        return cause_graph
