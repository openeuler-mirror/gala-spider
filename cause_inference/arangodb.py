from typing import List, Tuple, Dict

from pyArango.connection import Connection
from pyArango.database import Database
from pyArango.theExceptions import AQLQueryError

from spider.util import logger
from cause_inference.model import TopoNode, TopoEdge
from cause_inference.exceptions import DBException

_TIMESTAMP_COLL_NAME = 'Timestamps'
_OBSERVE_ENTITY_COLL_PREFIX = 'ObserveEntities'

CODE_OF_EDGE_COLL_NOT_FOUND = 404


def _get_collection_name(collection_type, ts_sec):
    return '{}_{}'.format(collection_type, ts_sec)


def connect_to_arangodb(arango_url, db_name):
    try:
        conn: Connection = Connection(arangoURL=arango_url)
    except ConnectionError as ex:
        raise DBException('Connect to arangodb error because {}'.format(ex)) from ex
    if not conn.hasDatabase(db_name):
        raise DBException('Arango database {} not found, please check!'.format(db_name))
    return conn.databases[db_name]


def query_all(db, aql_query, bind_vars=None, raw_results=True):
    res = []
    query_hdl = db.AQLQuery(aql_query, bindVars=bind_vars, rawResults=raw_results)
    for item in query_hdl:
        res.append(item)
    return res


def query_recent_topo_ts(db: Database, ts) -> int:
    bind_vars = {'@collection': _TIMESTAMP_COLL_NAME, 'ts': ts}
    aql_query = '''
    FOR t IN @@collection
      FILTER TO_NUMBER(t._key) <= @ts
      SORT t._key DESC
      LIMIT 1
      RETURN t._key
    '''
    try:
        query_res = query_all(db, aql_query, bind_vars)
    except AQLQueryError as ex:
        raise DBException(ex) from ex
    if len(query_res) == 0:
        raise DBException('Can not find topological graph at the abnormal timestamp {}'.format(ts))
    last_ts = query_res[0]
    return int(last_ts)


def query_topo_entities(db: Database, ts, query_options=None) -> List[TopoNode]:
    if not query_options:
        query_options = {}

    entity_coll_name = _get_collection_name(_OBSERVE_ENTITY_COLL_PREFIX, ts)
    bind_vars = {'@collection': entity_coll_name}
    bind_vars.update(query_options)
    filter_str = gen_filter_str(query_options)
    aql_query = '''
    FOR v IN @@collection
      {}
      return v
    '''.format(filter_str)
    try:
        query_res = query_all(db, aql_query, bind_vars)
    except AQLQueryError as ex:
        raise DBException(ex) from ex

    res = []
    for node in query_res:
        res.append(create_node_from_dict(node))
    return res


def gen_filter_str(query_options) -> str:
    if not query_options:
        return ''

    filter_options = ['v.{} == @{}'.format(k, k) for k in query_options]
    filter_str = 'filter ' + ' and '.join(filter_options)
    return filter_str


def query_subgraph(db, ts, start_entity_id, edge_collection, depth=1, query_options=None)\
        -> Tuple[Dict[str, TopoNode], Dict[str, TopoEdge]]:
    query_options = query_options or {}

    entity_coll_name = _get_collection_name(_OBSERVE_ENTITY_COLL_PREFIX, ts)
    start_node_id = '{}/{}'.format(entity_coll_name, start_entity_id)
    bind_vars = {
        '@collection': entity_coll_name,
        'depth': depth,
        'start_v': start_node_id,
    }
    bind_vars.update(query_options)

    filter_str = gen_filter_str(query_options)
    edge_coll_str = ', '.join(edge_collection)
    aql_query = '''
    WITH @@collection
    FOR v, e IN 1..@depth ANY @start_v
      {}
      options {{"uniqueVertices": "path"}}
      {}
      return {{"node": v, "edge": e}}
    '''.format(edge_coll_str, filter_str)
    try:
        query_res = query_all(db, aql_query, bind_vars)
    except AQLQueryError as ex:
        raise DBException(ex) from ex

    nodes = {}
    edges = {}
    for item in query_res:
        node = item.get('node')
        edge = item.get('edge')
        nodes.setdefault(node.get('_id'), create_node_from_dict(node))
        edges.setdefault(edge.get('_id'), create_edge_from_dict(edge))
    return nodes, edges


def query_cross_host_edges_detail(db: Database, edge_coll, ts) -> List[TopoEdge]:
    bind_vars = {
        '@coll': _get_collection_name(_OBSERVE_ENTITY_COLL_PREFIX, ts),
        '@edge': edge_coll,
        'ts': ts
    }
    aql_query = """
    for e in @@edge filter e.timestamp == @ts
        let from = (for v in @@coll filter v._id == e._from return v)
        let to = (for v in @@coll filter v._id == e._to return v)
        filter from[0].machine_id != to[0].machine_id
        return {edge: e, from: from, to: to}
    """
    try:
        query_res = query_all(db, aql_query, bind_vars)
    except AQLQueryError as ex:
        if ex.errors.get('code') == CODE_OF_EDGE_COLL_NOT_FOUND:
            logger.logger.debug(ex.message)
            return []
        raise DBException(ex) from ex

    res = []
    for item in query_res:
        edge = create_edge_from_dict(item.get('edge'))
        edge.from_node = create_node_from_dict(item.get('from')[0])
        edge.to_node = create_node_from_dict(item.get('to')[0])
        res.append(edge)
    return res


def create_node_from_dict(data: dict) -> TopoNode:
    return TopoNode(
        id=data.get('_id'),
        entity_id=data.get('_key'),
        entity_type=data.get('type'),
        machine_id=data.get('machine_id'),
        timestamp=data.get('timestamp'),
        raw_data=data
    )


def create_edge_from_dict(data: dict) -> TopoEdge:
    return TopoEdge(
        id=data.get('_id'),
        type=data.get('type'),
        from_id=data.get('_from'),
        to_id=data.get('_to')
    )
