import os

import yaml

from spider.util import logger


class CauseKeywordMgt:
    def __init__(self):
        self._entity_keywords = {}

    def load_keywords_from_yaml(self, path) -> bool:
        try:
            with open(os.path.abspath(path), 'r') as file:
                data = yaml.safe_load(file)
        except IOError as ex:
            logger.logger.warning(ex)
            return False

        self.load_keywords_from_dict(data)
        return True

    def load_keywords_from_dict(self, data: dict):
        self.load_entity_keywords(data.get('entity_keywords', {}))

    def load_entity_keywords(self, entity_keywords: dict):
        self._entity_keywords.update(entity_keywords)

    def get_keyword_of_entity(self, entity_type):
        return self._entity_keywords.get(entity_type, '')


cause_keyword_mgt = CauseKeywordMgt()
