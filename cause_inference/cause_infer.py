from typing import List, Dict

from scipy.stats import pearsonr
import numpy as np

from spider.util import logger
from spider.conf.observe_meta import RelationType, ObserveMetaMgt
from spider.collector import DataCollectorFactory

from cause_inference.model import Cause, MetricNodeId, MetricNode, CauseTree, HostTopo, TopoNode, TopoEdge
from cause_inference.model import AbnormalEvent
from cause_inference.model import is_virtual_metric
from cause_inference.causal_graph import CausalGraph
from cause_inference.exceptions import InferenceException
from cause_inference.config import infer_config
from cause_inference.rule_parser import rule_engine
from cause_inference.arangodb import connect_to_arangodb
from cause_inference.infer_policy import InferPolicy
from cause_inference.infer_policy import get_infer_policy
from cause_inference.output import format_infer_result
from cause_inference.db_mgt import ArangodbMgt, PromMgt
from cause_inference.trend import trend


class CauseLocator:
    def __init__(self, abn_kpi: AbnormalEvent, all_abn_metrics: List[AbnormalEvent], topo_db_mgt,
                 metric_db_mgt, infer_policy: InferPolicy, top_k):
        self.abn_kpi = abn_kpi
        self.all_abn_metrics = all_abn_metrics
        self.topo_db_mgt = topo_db_mgt
        self.metric_db_mgt = metric_db_mgt
        self.infer_policy = infer_policy
        self.top_k = top_k

        self.topo_ts = None

    @staticmethod
    def gen_host_causal_relations(host_topo: HostTopo) -> List[tuple]:
        return rule_engine.rule_parsing(host_topo.nodes, host_topo.edges)

    @staticmethod
    def filter_affected_metric_node_ids(affected_cause_nodes: List[MetricNode], causal_graph: CausalGraph)\
            -> List[MetricNodeId]:
        node_ids = set()
        for node in affected_cause_nodes:
            if node.node_id in causal_graph.metric_cause_graph:
                node_ids.add(node.node_id)
        return list(node_ids)

    @staticmethod
    def clear_virtual_cause(cause: Cause):
        for i in range(len(cause.path)):
            if is_virtual_metric(cause.path[i].node_id.metric_id):
                continue
            path = cause.path[i:]
            return Cause(path[0].node_id.metric_id, path[0].node_attrs.get('entity_id'), cause.cause_score, path)

    @staticmethod
    def filter_causes(causes: List[Cause]) -> List[Cause]:
        res = []
        for cause in causes:
            filtered_cause = CauseLocator.clear_virtual_cause(cause)
            if filtered_cause is not None:
                res.append(filtered_cause)
        return res

    def construct_causal_graph(self, entity_causal_relations: List[tuple], abn_metrics: List[AbnormalEvent],
                               topo_nodes: Dict[str, TopoNode]) -> CausalGraph:
        causal_graph = CausalGraph()

        # 构建实体因果图
        causal_graph.init_entity_cause_graph(entity_causal_relations, topo_nodes)
        causal_graph.add_abn_metrics(abn_metrics)

        self.calc_corr_score(causal_graph)
        causal_graph.filter_abn_metrics_by_corr_score()

        # 构建指标因果图
        rule_engine.add_rule_meta(causal_graph)
        causal_graph.init_metric_cause_graph()

        return causal_graph

    def locating(self) -> List[Cause]:
        self.init_topo_timestamp()

        abn_entity = self.topo_db_mgt.query_entity_by_id(self.abn_kpi.abnormal_entity_id, self.topo_ts)
        causes = self.host_locating(abn_entity, self.abn_kpi.abnormal_metric_id, self.top_k)

        return self.filter_causes(causes)

    def host_locating(self, abn_entity: TopoNode, abn_metric_id: str, top_k) -> List[Cause]:
        host_topo = self.topo_db_mgt.query_host_topo(abn_entity.machine_id, self.topo_ts)
        causal_graph = self.construct_host_causal_graph(host_topo)

        logger.logger.debug("Host metric cause graph edges are: {}".format(causal_graph.metric_cause_graph.edges))

        abn_metric_node_id = MetricNodeId(abn_entity.id, abn_metric_id)
        return self.infer_policy.infer(causal_graph.metric_cause_graph, abn_metric_node_id, top_k)

    def construct_host_causal_graph(self, host_topo: HostTopo) -> CausalGraph:
        host_causal_relations = self.gen_host_causal_relations(host_topo)
        return self.construct_causal_graph(host_causal_relations, self.all_abn_metrics, host_topo.nodes)

    def init_topo_timestamp(self):
        self.topo_ts = self.topo_db_mgt.query_recent_topo_ts(self.abn_kpi.timestamp // 1000)

    def calc_corr_score(self, causal_graph: CausalGraph):
        if not self.abn_kpi.hist_data:
            hist_data = self.metric_db_mgt.query_metric_hist_data(self.abn_kpi.abnormal_metric_id,
                                                                  self.abn_kpi.metric_labels,
                                                                  self.topo_ts)
            self.abn_kpi.set_hist_data(hist_data)

        for node_id, node_attrs in causal_graph.entity_cause_graph.nodes.items():
            metric_labels = node_attrs.get('raw_data')
            if not metric_labels:
                logger.logger.debug('Entity {} has no labels found'.format(node_id))
                continue

            abn_metrics = causal_graph.get_abnormal_metrics(node_id)
            for metric_id, metric_attrs in abn_metrics.items():
                metric_hist_data = self.metric_db_mgt.query_metric_hist_data(metric_id, metric_labels, self.topo_ts)

                data_trend = trend(metric_hist_data)
                metric_attrs.setdefault('real_trend', data_trend)

                corr = pearsonr(self.abn_kpi.hist_data, metric_hist_data)
                if np.isnan(corr[0]):
                    continue
                metric_attrs.setdefault('corr_score', abs(corr[0]))


class ClusterCauseLocator(CauseLocator):
    def __init__(self, abn_kpi: AbnormalEvent, all_abn_metrics: List[AbnormalEvent], topo_db_mgt,
                 metric_db_mgt, infer_policy: InferPolicy, top_k):
        super().__init__(abn_kpi, all_abn_metrics, topo_db_mgt, metric_db_mgt, infer_policy, top_k)

        self.cause_tree: CauseTree = CauseTree()
        self.all_cross_host_edges: List[TopoEdge] = []
        self.cross_host_edge_types = [RelationType.RUNS_ON.value, RelationType.STORE_IN.value]

    @staticmethod
    def gen_cross_causal_relations(affected_host_topo: HostTopo, neigh_topo: HostTopo, cross_edge: TopoEdge)\
            -> List[tuple]:
        topo_nodes = {}
        topo_nodes.update(affected_host_topo.nodes)
        topo_nodes.update(neigh_topo.nodes)
        topo_edges = {cross_edge.id: cross_edge}
        cross_causal_relations = rule_engine.cross_rule_parsing(topo_nodes, topo_edges)

        affected_causal_relations = []
        for causal_relation in cross_causal_relations:
            if causal_relation[1] in affected_host_topo.nodes:
                affected_causal_relations.append(causal_relation)

        return affected_causal_relations

    @staticmethod
    def get_neigh_entity(affected_machine_id: str, cross_edge: TopoEdge) -> TopoNode:
        from_node = cross_edge.from_node
        if from_node.machine_id != affected_machine_id:
            return from_node
        return cross_edge.to_node

    def locating(self) -> List[Cause]:
        self.init_topo_timestamp()
        self.init_all_cross_host_edges()

        abn_entity = self.topo_db_mgt.query_entity_by_id(self.abn_kpi.abnormal_entity_id, self.topo_ts)
        causes = self.host_locating(abn_entity, self.abn_kpi.abnormal_metric_id, 0)
        newly_cause_nodes = self.cause_tree.append_all_causes(causes)
        if len(newly_cause_nodes) == 0:
            return []

        self.cross_host_cause_locating(abn_entity.machine_id, newly_cause_nodes, 0)
        cluster_cause_graph = self.cause_tree.to_cause_graph()
        logger.logger.debug('Cluster metric cause graph edges are: {}'.format(cluster_cause_graph.edges))
        causes = self.infer_policy.infer(cluster_cause_graph,
                                         MetricNodeId(abn_entity.id, self.abn_kpi.abnormal_metric_id),
                                         self.top_k)

        return self.filter_causes(causes)

    def cross_host_cause_locating(self, affected_machine_id, affected_causes: List[MetricNode], top_k):
        logger.logger.debug('===Start cross host cause locating, affected machine id is:{}'.format(affected_machine_id))
        try:
            affected_host_topo = self.topo_db_mgt.query_host_topo(affected_machine_id, self.topo_ts)
        except InferenceException as ex:
            logger.logger.warning(ex)
            return
        cross_host_edges = self.filter_cross_host_edges(affected_machine_id)
        for cross_edge in cross_host_edges:
            neigh_entity = self.get_neigh_entity(affected_machine_id, cross_edge)
            try:
                neigh_topo = self.topo_db_mgt.query_host_topo(neigh_entity.machine_id, self.topo_ts)
            except InferenceException as ex:
                logger.logger.warning(ex)
                continue
            cross_causal_graph = self.construct_cross_host_causal_graph(affected_host_topo, neigh_topo, cross_edge)

            affected_metric_node_ids = self.filter_affected_metric_node_ids(affected_causes, cross_causal_graph)
            all_neigh_causes = []
            for start_metric_node_id in affected_metric_node_ids:
                causes = self.infer_policy.infer(cross_causal_graph.metric_cause_graph, start_metric_node_id, top_k)
                for cause in causes:
                    if cause.path[0].node_attrs.get('machine_id') != neigh_topo.machine_id:
                        logger.logger.debug('Cause(metric_id={}, entity_id={}) not in machine {}'.
                                            format(cause.metric_id, cause.entity_id, neigh_topo.machine_id))
                        continue
                    all_neigh_causes.append(cause)

            newly_cause_nodes = self.cause_tree.append_all_causes(all_neigh_causes)
            if len(newly_cause_nodes) > 0:
                self.cross_host_cause_locating(neigh_entity.machine_id, newly_cause_nodes, top_k)

    def filter_cross_host_edges(self, machine_id: str) -> List[TopoEdge]:
        filtered_edges = []
        for edge in self.all_cross_host_edges:
            if edge.from_node.machine_id == machine_id or edge.to_node.machine_id == machine_id:
                filtered_edges.append(edge)
        return filtered_edges

    def construct_cross_host_causal_graph(self, affected_host_topo: HostTopo, neigh_topo: HostTopo,
                                          cross_edge: TopoEdge) -> CausalGraph:
        cross_causal_relations = self.gen_cross_causal_relations(affected_host_topo, neigh_topo, cross_edge)
        neigh_causal_relations = self.gen_host_causal_relations(neigh_topo)

        causal_relations = []
        causal_relations.extend(cross_causal_relations)
        causal_relations.extend(neigh_causal_relations)
        topo_nodes = {}
        topo_nodes.update(affected_host_topo.nodes)
        topo_nodes.update(neigh_topo.nodes)

        return self.construct_causal_graph(causal_relations, self.all_abn_metrics, topo_nodes)

    def init_all_cross_host_edges(self):
        all_edges = []
        for r_type in self.cross_host_edge_types:
            try:
                query_res = self.topo_db_mgt.query_cross_host_edges_detail(r_type, self.topo_ts)
            except InferenceException as ex:
                logger.logger.warning(ex)
                continue
            all_edges.extend(query_res)
        self.all_cross_host_edges = all_edges


def cause_locating(abnormal_kpi: AbnormalEvent, abnormal_metrics: List[AbnormalEvent]):
    arango_conf = infer_config.arango_conf
    prom_conf = infer_config.prometheus_conf
    infer_conf = infer_config.infer_conf
    arango_db = connect_to_arangodb(arango_conf.get('url'), arango_conf.get('db_name'))
    arango_db_mgt = ArangodbMgt(arango_db, infer_conf.get('topo_depth'))
    collector = DataCollectorFactory.get_instance('prometheus', prom_conf)
    metric_db_mgt = PromMgt(collector, prom_conf.get('sample_duration'), prom_conf.get('step'), ObserveMetaMgt())

    infer_policy = get_infer_policy(infer_conf.get('infer_policy'))
    locator = ClusterCauseLocator(abnormal_kpi, abnormal_metrics, arango_db_mgt, metric_db_mgt, infer_policy,
                                  infer_conf.get('root_topk'))
    causes = locator.locating()
    if len(causes) == 0:
        return {}

    logger.logger.debug('=========inferring result: =============')
    for i, cause in enumerate(causes):
        logger.logger.debug('The top {} root metric output:'.format(i+1))
        logger.logger.debug('cause metric is: {}, cause entity is: {}, cause score is: {}'.format(
            cause.metric_id,
            cause.entity_id,
            cause.cause_score,
        ))

    res = format_infer_result(causes)
    return res
