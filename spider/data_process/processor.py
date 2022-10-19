from typing import List
from abc import ABCMeta
from abc import abstractmethod

from spider.entity_mgt.models import ObserveEntity


class DataProcessor(metaclass=ABCMeta):
    @abstractmethod
    def get_observe_entities(self, timestamp: float = None) -> List[ObserveEntity]:
        """
        获取所有的观测实例数据，并作为统一数据模型返回。
        例：
        输入：timestamp = 0
        输出：res = [
                 ObserveEntity(id="TCP_LINK_machine1", type="tcp_link", timestamp=0,
                               attrs={rx_bytes: 1, tx_bytes: 2, machine_id: "machine1"}),
                 ObserveEntity(id="TCP_LINK_machine2", type="tcp_link", timestamp=0,
                               attrs={rx_bytes: 3, tx_bytes: 4, machine_id: "machine2"}),
                 ObserveEntity(id="TASK_machine1", type="task", timestamp=0,
                               attrs={fork_count: 1, machine_id: "machine1"}),
             ]
        @param timestamp: 观测实例数据对应的时间戳
        @return: 所有的观测实例数据，以 List[ObserveEntity] 的形式返回。
        """
        pass
