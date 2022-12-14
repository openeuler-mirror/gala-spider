from dataclasses import dataclass
from dataclasses import field
from dataclasses import InitVar

from spider.util import logger
from spider.conf.observe_meta import ObserveMeta

ENTITYID_CONCATE_SIGN = '_'
RELATIONID_CONCATE_SIGN = '_'
MACHINE_ID_KEY_NAME = 'machine_id'


@dataclass
class ObserveEntity:
    id: str = field(init=False)
    type: str
    name: str
    level: str
    timestamp: float
    attrs: dict = field(init=False)
    observe_data: InitVar[dict]
    observe_meta: InitVar[ObserveMeta]

    def __post_init__(self, observe_data: dict, observe_meta: ObserveMeta):
        if not observe_data or not observe_meta:
            return

        self.attrs = {}
        for key in observe_meta.keys:
            if key in observe_data:
                self.attrs[key] = observe_data.get(key)
        for label in observe_meta.labels:
            if label in observe_data:
                self.attrs[label] = observe_data.get(label)
        metrics = {}
        for metric in observe_meta.metrics:
            if metric in observe_data:
                metrics[metric] = observe_data.get(metric)
        self.attrs.setdefault('metrics', metrics)

        self.id = ''
        if not self.type or not self.attrs or MACHINE_ID_KEY_NAME not in self.attrs:
            return
        ids = [self.attrs.get(MACHINE_ID_KEY_NAME), self.type]
        for key in observe_meta.keys:
            if key not in self.attrs:
                logger.logger.debug("Required key {} of observe type {} not exist.".format(key, self.type))
                return
            if key == MACHINE_ID_KEY_NAME:
                continue
            ids.append(str(self.attrs.get(key)))

        self.id = ENTITYID_CONCATE_SIGN.join(ids)


@dataclass
class Relation:
    id: str = field(init=False)
    type: str
    layer: str
    sub_entity: ObserveEntity
    obj_entity: ObserveEntity

    def __post_init__(self):
        self.id = ''
        if not self.type or self.sub_entity is None or self.obj_entity is None:
            return
        self.id = RELATIONID_CONCATE_SIGN.join([self.type, self.sub_entity.id, self.obj_entity.id])
