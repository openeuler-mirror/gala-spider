from typing import List

from spider.collector import DataCollector, DataRecord
from spider.conf.observe_meta import RelationType, EntityType, ObserveMetaMgt
from spider.exceptions import MetadataException
from spider.util import logger

from cause_inference.arangodb import query_cross_host_edges_detail
from cause_inference.arangodb import query_recent_topo_ts
from cause_inference.arangodb import query_subgraph
from cause_inference.arangodb import query_topo_entities
from cause_inference.config import infer_config
from cause_inference.exceptions import InferenceException
from cause_inference.model import HostTopo, TopoNode, TopoEdge


class ArangodbMgt:
    def __init__(self, db, topo_depth):
        self.db = db
        self.topo_depth = topo_depth

        self.topo_edge_types = [
            RelationType.BELONGS_TO.value,
            RelationType.RUNS_ON.value
        ]

    def query_host_topo(self, machine_id, ts_sec) -> HostTopo:
        query_options = {
            'type': EntityType.HOST.value,
            'machine_id': machine_id
        }
        host_entities = query_topo_entities(self.db, ts_sec, query_options=query_options)
        if len(host_entities) == 0:
            raise InferenceException('Can not find machine {} satisfied.'.format(machine_id))
        if len(host_entities) > 1:
            raise InferenceException('Multiple hosts with the same machine id {} found.'.format(machine_id))

        host_entity = host_entities[0]
        nodes, edges = query_subgraph(self.db, ts_sec, host_entity.entity_id, self.topo_edge_types,
                                      depth=self.topo_depth,
                                      query_options={'machine_id': machine_id})
        nodes.setdefault(host_entity.id, host_entity)
        for edge in edges.values():
            edge.from_node = nodes.get(edge.from_id)
            edge.to_node = nodes.get(edge.to_id)

        return HostTopo(machine_id, nodes, edges)

    def query_entity_by_id(self, entity_id, ts_sec) -> TopoNode:
        entities = query_topo_entities(self.db, ts_sec, query_options={'_key': entity_id})
        if len(entities) == 0:
            raise InferenceException('Can not find entity {} satisfied.'.format(entity_id))
        if len(entities) > 1:
            raise InferenceException('Multiple entities with the same entity id {} found.'.format(entity_id))
        return entities[0]

    def query_recent_topo_ts(self, ts_sec) -> int:
        recent_ts = query_recent_topo_ts(self.db, ts_sec)
        if ts_sec - recent_ts > infer_config.infer_conf.get('tolerated_bias'):
            raise InferenceException('The queried topological graph is too old, topo timestamp={}.'.format(recent_ts))
        return recent_ts

    def query_cross_host_edges_detail(self, edge_type, ts_sec) -> List[TopoEdge]:
        return query_cross_host_edges_detail(self.db, edge_type, ts_sec)


class PromMgt:
    def __init__(self, collector: DataCollector, sample_duration, sample_step, obsv_meta_mgt: ObserveMetaMgt):
        self.collector = collector
        self.sample_duration = sample_duration
        self.sample_step = sample_step
        self.obsv_meta_mgt = obsv_meta_mgt

    def query_metric_hist_data(self, metric_id, metric_labels, end_ts) -> list:
        start_ts = end_ts - self.sample_duration
        try:
            query_options = self.obsv_meta_mgt.get_entity_keys_of_metric(metric_id, metric_labels)
        except MetadataException as ex:
            logger.logger.debug(ex)
            return self.fill_empty_hist_data()
        records = self.collector.get_range_data(metric_id, start_ts, end_ts, query_options=query_options,
                                                step=self.sample_step)
        if len(records) == 0:
            logger.logger.warning('No history data of the metric {}'.format(metric_id))
            return self.fill_empty_hist_data()

        hist_data = self.fill_hist_data(records, end_ts)
        return hist_data

    def fill_hist_data(self, records: List[DataRecord], end_ts: float) -> list:
        sample_num = self.sample_duration // self.sample_step
        start_ts = end_ts - self.sample_duration
        res = self.fill_empty_hist_data()
        record_len = len(records)
        i = 0
        j = 0
        while i < sample_num and j < record_len:
            ts = start_ts + (i + 1) * self.sample_step
            if ts < records[j].timestamp:
                i += 1
                continue
            if records[j].timestamp + 2 * self.sample_step < ts:
                j += 1
                continue
            res[i] = float(records[j].metric_value)
            j += 1
            i += 1
        return res

    def fill_empty_hist_data(self):
        sample_num = self.sample_duration // self.sample_step
        return [0.0] * sample_num
