from typing import List
from typing import Dict
from typing import Tuple

from spider.conf.observe_meta import ObserveMetaMgt
from spider.conf.observe_meta import ObserveMeta
from spider.conf.observe_meta import EntityType
from spider.conf.observe_meta import DirectRelationMeta
from spider.conf.observe_meta import RelationSideType
from spider.conf.observe_meta import RelationType
from spider.conf.observe_meta import RelationLayerType
from spider.entity_mgt.models import ObserveEntity
from spider.entity_mgt.models import Relation

ConnectPair = Tuple[ObserveEntity, ObserveEntity]


class ObserveEntityCreator:
    @staticmethod
    def create_observe_entity(entity_type: str, entity_attrs: dict, entity_meta: ObserveMeta = None) -> ObserveEntity:
        """
        根据采集的观测实例数据和对应类型的观测对象配置元数据，创建一个观测实例对象。
        @param entity_type: 观测对象类型
        @param entity_attrs: 观测实例数据
        @param entity_meta: 观测对象配置元数据
        @return: 返回类型为 entity_type 的一个观测对象实例
        """
        if entity_meta is None:
            entity_meta = ObserveMetaMgt().get_observe_meta(entity_type)
            if entity_meta is None:
                return None

        entity = ObserveEntity(type=entity_type,
                               name=entity_attrs.get(entity_meta.name),
                               level=entity_meta.level,
                               timestamp=entity_attrs.get('timestamp'),
                               observe_data=entity_attrs,
                               observe_meta=entity_meta)

        return None if not entity.id else entity

    @staticmethod
    def create_logical_observe_entities(observe_entities: List[ObserveEntity]) -> List[ObserveEntity]:
        res: List[ObserveEntity] = []

        observe_entity_map: Dict[str, List[ObserveEntity]] = {}
        for entity in observe_entities:
            val = observe_entity_map.setdefault(entity.type, [])
            val.append(entity)

        processes = observe_entity_map.get(EntityType.PROCESS.value, [])
        containers = observe_entity_map.get(EntityType.CONTAINER.value, [])
        app_instances = ObserveEntityCreator._create_app_instance_observe_entities(processes)
        res.extend(app_instances)
        pods = ObserveEntityCreator._create_pod_observe_entities(containers)
        res.extend(pods)

        return res

    @staticmethod
    def _create_app_instance_observe_entities(processes: List[ObserveEntity]) -> List[ObserveEntity]:
        app_inst_meta = ObserveMetaMgt().get_observe_meta(EntityType.APPINSTANCE.value)
        if not app_inst_meta:
            return []
        entity_map: Dict[str, ObserveEntity] = {}

        for process in processes:
            entity = ObserveEntityCreator._create_entity_from(process, app_inst_meta)
            if not entity or not entity.id:
                continue

            entity_map.setdefault(entity.id, entity)
            entity_attrs = entity_map.get(entity.id).attrs
            entity_attrs.setdefault('processes', [])
            entity_attrs.get('processes').append(process.id)

        return list(entity_map.values())

    @staticmethod
    def _create_pod_observe_entities(containers: List[ObserveEntity]) -> List[ObserveEntity]:
        pod_meta = ObserveMetaMgt().get_observe_meta(EntityType.POD.value)
        if not pod_meta:
            return []
        entity_map: Dict[str, ObserveEntity] = {}

        for container in containers:
            entity = ObserveEntityCreator._create_entity_from(container, pod_meta)
            if not entity or not entity.id:
                continue
            entity_map.setdefault(entity.id, entity)
        return list(entity_map.values())

    @staticmethod
    def _create_entity_from(src_entity: ObserveEntity, target_entity_meta: ObserveMeta) -> ObserveEntity:
        target_attrs = {}
        for key in target_entity_meta.keys:
            if key not in src_entity.attrs:
                return None
            target_attrs[key] = src_entity.attrs.get(key)
        for label in target_entity_meta.labels:
            if label in src_entity.attrs:
                target_attrs[label] = src_entity.attrs.get(label)

        target_entity = ObserveEntity(type=target_entity_meta.type,
                                      name=target_attrs.get(target_entity_meta.name),
                                      level=target_entity_meta.level,
                                      timestamp=src_entity.timestamp,
                                      observe_data=target_attrs,
                                      observe_meta=target_entity_meta)
        return target_entity


class DirectRelationCreator:
    @staticmethod
    def create_relation(sub_entity: ObserveEntity, obj_entity: ObserveEntity,
                        relation_meta: DirectRelationMeta) -> Relation:
        """
        创建一个直接的关联关系。
        @param sub_entity: 关系的主体，是一个观测对象实例
        @param obj_entity: 关系的客体，是一个观测对象实例
        @param relation_meta: 关系的元数据
        @return: 返回一个直接的关联关系
        """
        if sub_entity is None or obj_entity is None or relation_meta is None:
            return None
        if sub_entity.id == obj_entity.id:
            return None
        if sub_entity.type != relation_meta.from_type or obj_entity.type != relation_meta.to_type:
            return None

        for match in relation_meta.matches:
            if sub_entity.attrs.get(match.from_) != obj_entity.attrs.get(match.to):
                return None

        for require in relation_meta.requires:
            entity = sub_entity if RelationSideType.FROM.value == require.side else obj_entity
            if entity.attrs.get(require.label) != require.value:
                return None

        for conflict in relation_meta.conflicts:
            if sub_entity.attrs.get(conflict.from_) == obj_entity.attrs.get(conflict.to):
                return None

        for like in relation_meta.likes:
            entity = sub_entity if RelationSideType.FROM.value == like.side else obj_entity
            if like.label not in entity.attrs or like.value not in entity.attrs.get(like.label):
                return None

        relation = Relation(relation_meta.id, relation_meta.layer, sub_entity, obj_entity)
        return relation

    @staticmethod
    def create_relations(observe_entities: List[ObserveEntity]) -> List[Relation]:
        """
        计算所有观测实例之间的直接关联关系。
        @param observe_entities: 观测实例的集合
        @return: 返回所有观测实例之间存在的直接关联关系的集合
        """
        observe_entity_map: Dict[str, List[ObserveEntity]] = {}
        for entity in observe_entities:
            val = observe_entity_map.setdefault(entity.type, [])
            val.append(entity)

        res: List[Relation] = []
        for sub_entity in observe_entities:
            observe_meta = ObserveMetaMgt().get_observe_meta(sub_entity.type)
            for relation_meta in observe_meta.depending_items:
                if not isinstance(relation_meta, DirectRelationMeta):
                    continue
                obj_entities = observe_entity_map.get(relation_meta.to_type)
                if obj_entities is None:
                    continue
                for obj_entity in obj_entities:
                    relation = DirectRelationCreator.create_relation(sub_entity, obj_entity, relation_meta)
                    if relation is not None:
                        res.append(relation)

        return res


class IndirectRelationCreator:
    @staticmethod
    def create_relations(observe_entities: List[ObserveEntity],
                         direct_relations: List[Relation]) -> List[Relation]:
        """
        计算所有观测实例之间的间接关联关系。
        @param observe_entities: 观测实例的集合
        @param direct_relations: 所有观测实例 observe_entities 之间存在的直接关联关系的集合
        @return: 返回所有观测实例之间的间接关联关系的集合
        """
        res: List[Relation] = []

        connect_relations = IndirectRelationCreator.create_connect_relations(observe_entities, direct_relations)
        res.extend(connect_relations)

        return res

    @staticmethod
    def create_connect_relation(sub_entity: ObserveEntity, obj_entity: ObserveEntity) -> Relation:
        """
        创建一个间接的 connect 关系。
        @param sub_entity: 关系的主体，是一个观测对象实例
        @param obj_entity: 关系的客体，是一个观测对象实例
        @return: 返回一个间接的连接关系。
        """
        if sub_entity is None or obj_entity is None:
            return None
        if sub_entity.id == obj_entity.id:
            return None
        if not ObserveMetaMgt().check_relation(RelationType.CONNECT.value, RelationLayerType.INDIRECT.value,
                                               sub_entity.type, obj_entity.type):
            return None

        relation = Relation(RelationType.CONNECT.value, RelationLayerType.INDIRECT.value, sub_entity, obj_entity)
        return relation

    @staticmethod
    def create_connect_relations(observe_entities: List[ObserveEntity],
                                 direct_relations: List[Relation]) -> List[Relation]:
        """
        计算所有观测实例之间的间接的 connect 关系。
        @param observe_entities: 观测实例的集合
        @param direct_relations: 所有观测实例 observe_entities 之间存在的直接关联关系的集合
        @return: 返回所有观测实例之间的间接的 connect 关系的集合
        """
        res: List[Relation] = []
        observe_entity_map: Dict[str, ObserveEntity] = {}
        direct_relation_map: Dict[str, List[Relation]] = {}
        belongs_to_map: Dict[str, List[Relation]] = {}

        for entity in observe_entities:
            observe_entity_map.setdefault(entity.id, entity)

        for relation in direct_relations:
            val = direct_relation_map.setdefault(relation.type, [])
            val.append(relation)
            if relation.type == RelationType.BELONGS_TO.value:
                belongs_to_map.setdefault(relation.sub_entity.id, []).append(relation)

        connect_pairs = IndirectRelationCreator._create_connect_pairs(direct_relation_map)
        res.extend(IndirectRelationCreator._create_connect_relations_by_belongs_to(connect_pairs, belongs_to_map))
        res = IndirectRelationCreator._rm_dup_conn_relations(res)

        return res

    @staticmethod
    def _create_connect_pairs(direct_relation_map: Dict[str, List[Relation]]) -> List[ConnectPair]:
        res: List[ConnectPair] = []

        res.extend(IndirectRelationCreator._create_connect_pairs_by_is_peer(direct_relation_map))
        res.extend(IndirectRelationCreator._create_connect_pairs_by_is_client_server(direct_relation_map))

        return res

    @staticmethod
    def _create_connect_pairs_by_is_peer(direct_relation_map: Dict[str, List[Relation]]) -> List[ConnectPair]:
        res: List[ConnectPair] = []

        is_peer_relations = direct_relation_map.get(RelationType.IS_PEER.value, [])
        for is_peer_relation in is_peer_relations:
            res.append((is_peer_relation.sub_entity, is_peer_relation.obj_entity))

        return res

    @staticmethod
    def _create_connect_pairs_by_is_client_server(direct_relation_map: Dict[str, List[Relation]]) -> List[ConnectPair]:
        res: List[ConnectPair] = []

        is_server_relations = direct_relation_map.get(RelationType.IS_SERVER.value, [])
        is_client_relations = direct_relation_map.get(RelationType.IS_CLIENT.value, [])
        for is_server_relation in is_server_relations:
            for is_client_relation in is_client_relations:
                if is_server_relation.obj_entity == is_client_relation.obj_entity:
                    res.append((is_client_relation.sub_entity, is_server_relation.sub_entity))

        return res

    @staticmethod
    def _get_all_leaf_entities(target_relation_map: Dict[str, List[Relation]], entity_id) -> List[ObserveEntity]:
        """
        以指定实体（entity_id）为起点，沿着指定关系（target_relation_map）链找到所有叶子实体放入结果列表中。

        例如，对于 procA --> belongs_to --> containerA --> belongs_to --> podA 形成 belongs_to 关系链中，
        最终只会将 podA 实体加入到结果列表中。

        功能说明：该函数用于聚合不同部署方式的应用之间的 connect 关系。比如，如果两个 Pod 之间存在多条 tcp 连接关系，那么最终
            只会在两个 Pod 之间建立一条 connect 关系，并忽略属于两个 Pod 的所有上层 container、process 之间的 connect 关系。
        实现说明：考虑到 belongs_to 关系可能存在一对多的情况，这里使用 dfs 进行遍历。
        """
        res = []
        selected = set()
        target_entity_types = {EntityType.PROCESS.value, EntityType.CONTAINER.value, EntityType.POD.value}

        def dfs(entity: ObserveEntity):
            if entity.id in selected:
                return
            selected.add(entity.id)

            is_leaf = True
            successors = target_relation_map.get(entity.id, [])
            for succ in successors:
                if succ.obj_entity.type in target_entity_types:
                    is_leaf = False
                    dfs(succ.obj_entity)
            if is_leaf:
                res.append(entity)

        selected.add(entity_id)
        for relation in target_relation_map.get(entity_id, []):
            if relation.obj_entity.type in target_entity_types:
                dfs(relation.obj_entity)
        return res

    @staticmethod
    def _create_connect_relations_by_belongs_to(connect_pairs: List[ConnectPair],
                                                belongs_to_map: Dict[str, List[Relation]]) -> List[Relation]:
        res: List[Relation] = []
        for entity1, entity2 in connect_pairs:
            belongs_to_entities1 = IndirectRelationCreator._get_all_leaf_entities(belongs_to_map, entity1.id)
            belongs_to_entities2 = IndirectRelationCreator._get_all_leaf_entities(belongs_to_map, entity2.id)

            for _entity1 in belongs_to_entities1:
                for _entity2 in belongs_to_entities2:
                    relation = IndirectRelationCreator.create_connect_relation(_entity1, _entity2)
                    if relation is not None:
                        res.append(relation)

        return res

    @staticmethod
    def _rm_dup_conn_relations(conn_relations: List[Relation]) -> List[Relation]:
        res: List[Relation] = []
        unique = set()
        for relation in conn_relations:
            if not relation.id or relation.id in unique:
                continue
            unique.add(relation.id)
            res.append(relation)
        return res
