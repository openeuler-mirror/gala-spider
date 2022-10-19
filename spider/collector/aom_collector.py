import time
from abc import ABCMeta, abstractmethod

import requests

from spider.util import logger
from spider.exceptions import ConfigException
from .prometheus_collector import PrometheusCollector


class AomAuth(metaclass=ABCMeta):
    @abstractmethod
    def set_auth_info(self, headers: dict):
        pass


class AppCodeAuth(AomAuth):
    def __init__(self, app_code: str):
        self._app_code = app_code

    def set_auth_info(self, headers: dict):
        headers['X-Apig-AppCode'] = self._app_code


class TokenAuth(AomAuth):
    def __init__(self, iam_user_name: str, iam_password: str, iam_domain: str, iam_server: str, verify: bool = False):
        self._iam_user_name = iam_user_name
        self._iam_password = iam_password
        self._iam_domain = iam_domain
        self._iam_server = iam_server
        self._verify = verify

        self._token: str = ''
        self._expires_at: int = 0
        # token 到期前 1 小时更新 token
        self._expire_duration: int = 3600

        self._token_api = '/v3/auth/tokens'

    @property
    def token(self):
        if not self._token or self.is_token_expired():
            self.update_token()
        return self._token

    def set_auth_info(self, headers: dict):
        headers['X-Auth-Token'] = self.token

    def update_token(self):
        headers = {
            'Content-Type': 'application/json;charset=utf8'
        }
        params = {
            'nocatalog': 'true'
        }
        body = {
            'auth': {
                'identity': {
                    'methods': ['password'],
                    'password': {
                        'user': {
                            'domain': {
                                'name': self._iam_domain
                            },
                            'name': self._iam_user_name,
                            'password': self._iam_password
                        }
                    }
                },
                'scope': {
                    'domain': {
                        'name': self._iam_domain
                    }
                }
            }
        }
        url = self._iam_server + self._token_api
        try:
            resp = requests.post(url, json=body, headers=headers, params=params, verify=self._verify)
        except requests.RequestException as ex:
            logger.logger.error(ex)
            return
        try:
            resp_body = resp.json()
        except requests.RequestException as ex:
            logger.logger.error(ex)
            return
        if resp.status_code != 201:
            logger.logger.error('Failed to request {}, error is {}'.format(url, resp_body))
            return
        expires_at = resp_body.get('token', {}).get('expires_at')
        if not self._transfer_expire_time(expires_at):
            logger.logger.error('Can not transfer expire time: {}'.format(expires_at))
            return
        self._token = resp.headers.get('X-Subject-Token')

    def is_token_expired(self) -> bool:
        return int(time.time()) + self._expire_duration > self._expires_at

    def _transfer_expire_time(self, s_time: str) -> bool:
        try:
            expires_at_arr = time.strptime(s_time, '%Y-%m-%dT%H:%M:%S.%fZ')
        except ValueError as ex:
            logger.logger.error(ex)
            return False
        self._expires_at = int(time.mktime(expires_at_arr))
        return True


class AomCollector(PrometheusCollector):
    def __init__(self, aom_server: str, project_id: str, aom_auth: AomAuth, step: int):
        self._project_id = project_id
        self._aom_auth = aom_auth

        instant_api = '/v1/{}/aom/api/v1/query'.format(self._project_id)
        range_api = '/v1/{}/aom/api/v1/query_range'.format(self._project_id)
        super().__init__(aom_server, instant_api, range_api, step)

    def set_instant_req_info(self, metric_id: str, timestamp: float, **kwargs) -> dict:
        req_data = super().set_instant_req_info(metric_id, timestamp, **kwargs)
        headers = {}
        self._aom_auth.set_auth_info(headers)
        req_data.update({'headers': headers})
        return req_data

    def set_range_req_info(self, metric_id: str, start: float, end: float, **kwargs) -> dict:
        req_data = super().set_range_req_info(metric_id, start, end, **kwargs)
        headers = {}
        self._aom_auth.set_auth_info(headers)
        req_data.update({'headers': headers})
        return req_data


def create_aom_auth(auth_type: str, auth_info: dict) -> AomAuth:
    if auth_type == 'appcode':
        return AppCodeAuth(auth_info.get('app_code'))
    elif auth_type == 'token':
        return TokenAuth(
            auth_info.get('iam_user_name'),
            auth_info.get('iam_password'),
            auth_info.get('iam_domain'),
            auth_info.get('iam_server'),
            verify=auth_info.get('ssl_verify')
        )
    raise ConfigException('Unsupported aom auth type: {}, please check'.format(auth_type))


def create_aom_collector(aom_conf: dict) -> AomCollector:
    aom_auth = create_aom_auth(aom_conf.get('auth_type'), aom_conf.get('auth_info'))
    return AomCollector(aom_conf.get('base_url'), aom_conf.get('project_id'), aom_auth, aom_conf.get('step'))
