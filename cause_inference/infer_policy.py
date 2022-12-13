import random
from abc import ABC
from abc import abstractmethod
from typing import List

import networkx as nx

from spider.util import logger
from cause_inference.model import Cause, MetricNode, MetricNodeId
from cause_inference.model import is_virtual_metric
from cause_inference.exceptions import InferenceException


class InferPolicy(ABC):
    @abstractmethod
    def infer(self, cause_graph: nx.DiGraph, target_node_id, top_k: int) -> List[Cause]:
        pass


class RandomWalkPolicy(InferPolicy):
    def __init__(self, rou=0.05, random_walk_round=10000, window_size=1000):
        self.rou = rou
        self.random_walk_round = random_walk_round
        if self.random_walk_round <= 0:
            raise InferenceException('The walk round of random walk algorithm can not be less than zero')
        self.window_size = window_size
        self.transfer_matrix = {}

    def infer(self, cause_graph: nx.DiGraph, target_node_id, top_k: int) -> List[Cause]:
        # 计算转移概率矩阵
        self.transfer_matrix.clear()
        for node_id in cause_graph.nodes:
            self.calc_transfer_probs(node_id, cause_graph)

        walk_nums = self.one_order_random_walk(target_node_id)
        cause_res = list(walk_nums.items())
        cause_res = sorted(cause_res, key=lambda k: k[1], reverse=True)
        cause_res = cause_res[:top_k]

        res = []
        for item in cause_res:
            node_id = item[0]
            score = item[1]
            try:
                uni_score = score / self.random_walk_round
            except ZeroDivisionError as ex:
                raise InferenceException(ex) from ex
            cause = Cause(node_id[1], node_id[0], uni_score)
            res.append(cause)

        return res

    def calc_transfer_probs(self, src_node_id, cause_graph: nx.DiGraph):
        probs = self.transfer_matrix.setdefault(src_node_id, {})

        # 计算前向转移概率
        max_corr = 0
        for node_id in cause_graph.pred:
            corr = abs(cause_graph.nodes[node_id].get('abnormal_score', 0))
            max_corr = max(max_corr, corr)
            probs.setdefault(node_id, corr)

        # 计算后向转移概率
        for node_id in cause_graph.succ:
            corr = abs(cause_graph.nodes[node_id].get('abnormal_score', 0))
            probs.setdefault(node_id, corr * self.rou)

        # 计算自向转移概率
        corr = max(0, abs(cause_graph.nodes[src_node_id].get('abnormal_score', 0)) - max_corr)
        probs.setdefault(src_node_id, corr)

        # 正则化
        total = sum(probs.values())
        for node_id, corr in probs.items():
            try:
                probs[node_id] = corr / total
            except ZeroDivisionError as ex:
                raise InferenceException('Sum of transition probability can not be zero') from ex

    def one_order_random_walk(self, start_node_id):
        walk_nums = {}
        rwr = self.random_walk_round
        curr_node_id = start_node_id
        round_ = 0
        while round_ < rwr:
            next_node_id = self.get_next_walk_node(curr_node_id)
            num = walk_nums.setdefault(next_node_id, 0)
            walk_nums.update({next_node_id: num + 1})
            round_ += 1
            curr_node_id = next_node_id

        return walk_nums

    def get_next_walk_node(self, curr_node_id):
        # 随机选择
        probs = self.transfer_matrix.get(curr_node_id)
        prob = random.random()
        next_node_id = curr_node_id
        for node_id, node_prob in probs.items():
            if prob < node_prob:
                next_node_id = node_id
                break
            prob -= node_prob

        return next_node_id


class DfsPolicy(InferPolicy):
    @staticmethod
    def get_node_cause_score(node_attrs: dict):
        return node_attrs.get('corr_score', 0)

    @staticmethod
    def calc_path_score(path: List[MetricNode]):
        length = len(path) - 1
        if length < 1:
            return 0.0
        total_score = 0.0
        num_of_valid_node = 0
        for node in path[:length]:
            if is_virtual_node(node.node_id):
                continue
            total_score += DfsPolicy.get_node_cause_score(node.node_attrs)
            num_of_valid_node += 1
        if num_of_valid_node != 0:
            total_score /= num_of_valid_node
        return total_score

    @staticmethod
    def get_all_paths_to_abn_node(abn_node_id, cause_graph: nx.DiGraph) -> List[MetricNode]:
        paths = []
        path = []
        node_selected = set()

        def dfs_path(node_id):
            has_pred = False
            for pred_node_id in cause_graph.predecessors(node_id):
                has_pred = True
                if pred_node_id in node_selected:
                    logger.logger.warning('Circle exist in cause graph, please check.')
                    continue
                node_selected.add(pred_node_id)
                path.append(MetricNode(pred_node_id, cause_graph.nodes[pred_node_id]))
                dfs_path(pred_node_id)
                path.pop()
                node_selected.remove(pred_node_id)
            if not has_pred:
                paths.append(path[::-1])
                return

        node_selected.add(abn_node_id)
        path.append(MetricNode(abn_node_id, cause_graph.nodes[abn_node_id]))
        dfs_path(abn_node_id)
        return paths

    @staticmethod
    def get_scored_paths(paths) -> list:
        scored_paths = []
        for path in paths:
            scored_paths.append({
                'score': DfsPolicy.calc_path_score(path),
                'path': path
            })
        return scored_paths

    @staticmethod
    def get_top_paths(scored_paths, top_k) -> list:
        top_paths = []
        node_selected = set()
        metric_selected = set()
        for scored_path in scored_paths:
            if len(top_paths) == top_k:
                break
            cause_node: MetricNode = scored_path.get('path')[0]
            machine_id = cause_node.node_attrs.get('machine_id')
            if cause_node.node_id in node_selected:
                continue
            if (machine_id, cause_node.node_id.metric_id) in metric_selected:
                continue
            node_selected.add(cause_node.node_id)
            metric_selected.add((machine_id, cause_node.node_id.metric_id))

            top_paths.append(scored_path)

        return top_paths

    @staticmethod
    def parse_causes(top_paths) -> List[Cause]:
        res = []
        for item in top_paths:
            path = item.get('path')
            cause = Cause(path[0].node_id.metric_id, path[0].node_attrs.get('entity_id'), item.get('score'), path)
            res.append(cause)
        return res

    def infer(self, cause_graph: nx.DiGraph, target_node_id, top_k: int) -> List[Cause]:
        if target_node_id not in cause_graph.nodes:
            return []

        paths = self.get_all_paths_to_abn_node(target_node_id, cause_graph)
        scored_paths = self.get_scored_paths(paths)
        scored_paths = sorted(scored_paths, key=lambda k: k['score'], reverse=True)
        if top_k > 0:
            top_paths = self.get_top_paths(scored_paths, top_k)
        else:
            top_paths = scored_paths

        return self.parse_causes(top_paths)


def is_virtual_node(node_id: MetricNodeId) -> bool:
    return is_virtual_metric(node_id.metric_id)


def get_infer_policy(policy: str, **options) -> InferPolicy:
    if policy == 'dfs':
        return DfsPolicy()
    if policy == 'rw':
        return RandomWalkPolicy(**options)
    raise InferenceException('Unsupported infer policy {}'.format(policy))
