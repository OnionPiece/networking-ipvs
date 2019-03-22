# Copyright 2018
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


import abc
import six

from oslo_config import cfg
from oslo_log import log as logging

from neutron.api import extensions
from neutron.api.v2 import attributes as attr
from neutron.api.v2 import base
from neutron.api.v2 import resource_helper
from neutron import manager
from neutron.plugins.common import constants
from neutron.services import service_base
from neutron_lib import exceptions as nexception

from networking_ipvs.common import constants as const


LOG = logging.getLogger(__name__)


NETWORKING_IPVS_PREFIX = "/ipvs"
SCHEDULERS = const.SUPPORTED_SCHEDULERS
FORWARD_METHODS = const.SUPPORTED_FORWARD_METHODS
RESOURCE_TYPES = const.SUPPORTED_RESOURCE_TYPES


def _validate_terget_tenant(data, valid_values=None):
    if data is not None:
        if data != 'default':
            return attr._validate_uuid(data)


attr.validators['type:uuid_default_or_none'] = _validate_terget_tenant


RESOURCE_ATTRIBUTE_MAP = {
    const.IPVS_LOADBALANCERS: {
        const.ID: {'allow_post': False, 'allow_put': False,
                   'validate': {'type:uuid': None},
                   'is_visible': True, 'primary_key': True},
        'tenant_id': {'allow_post': True, 'allow_put': False,
                      'validate': {'type:not_empty_string':
                                   attr.TENANT_ID_MAX_LEN},
                      'required_by_policy': True,
                      'is_visible': True},
        'name': {'allow_post': True, 'allow_put': True,
                 'validate': {'type:string': attr.NAME_MAX_LEN},
                 'default': '',
                 'is_visible': True},
        'description': {'allow_post': True, 'allow_put': True,
                        'validate': {'type:string': attr.DESCRIPTION_MAX_LEN},
                        'is_visible': True, 'default': ''},
        const.VIRTUALSERVERS: {'allow_post': False, 'allow_put': False,
                               'is_visible': True},
        const.ADMIN_STATE_UP: {'allow_post': True, 'allow_put': True,
                               'default': True,
                               'convert_to': attr.convert_to_boolean,
                               'is_visible': True},
    },
    const.IPVS_VIRTUALSERVERS: {
        const.ID: {'allow_post': False, 'allow_put': False,
                   'validate': {'type:uuid': None},
                   'is_visible': True, 'primary_key': True},
        'tenant_id': {'allow_post': True, 'allow_put': False,
                      'validate': {'type:not_empty_string':
                                   attr.TENANT_ID_MAX_LEN},
                      'required_by_policy': True,
                      'is_visible': True},
        'name': {'allow_post': True, 'allow_put': True,
                 'validate': {'type:string': attr.NAME_MAX_LEN},
                 'default': '',
                 'is_visible': True},
        'ipvs_loadbalancer_id': {'allow_post': True, 'allow_put': False,
                                 'validate': {'type:uuid': None},
                                 'is_visible': True},
        'neutron_network_id': {'allow_post': True, 'allow_put': False,
                               'validate': {'type:uuid': None},
                               'is_visible': True},
        const.LISTEN_IP: {'allow_post': True, 'allow_put': False,
                          'validate': {'type:ip_address_or_none': None},
                          'is_visible': True},
        const.LISTEN_PORT: {'allow_post': True, 'allow_put': False,
                            'validate': {'type:range': [0, 65535]},
                            'convert_to': attr.convert_to_int,
                            'is_visible': True},
        const.ADMIN_STATE_UP: {'allow_post': True, 'allow_put': True,
                               'default': True,
                               'convert_to': attr.convert_to_boolean,
                               'is_visible': True},
        const.SCHEDULER: {'allow_post': True, 'allow_put': True,
                          'validate': {'type:values': SCHEDULERS},
                          'is_visible': True},
        const.FORWARD_METHOD: {'allow_post': True, 'allow_put': False,
                               'validate': {'type:values': FORWARD_METHODS},
                               'is_visible': True},
        const.REALSERVERS: {'allow_post': False, 'allow_put': False,
                            'is_visible': True},
    },
    const.IPVS_REALSERVERS: {
        const.ID: {'allow_post': False, 'allow_put': False,
                   'validate': {'type:uuid': None},
                   'is_visible': True, 'primary_key': True},
        'tenant_id': {'allow_post': True, 'allow_put': False,
                      'validate': {'type:not_empty_string':
                                   attr.TENANT_ID_MAX_LEN},
                      'required_by_policy': True,
                      'is_visible': True},
        'name': {'allow_post': True, 'allow_put': True,
                 'validate': {'type:string': attr.NAME_MAX_LEN},
                 'default': '',
                 'is_visible': True},
        const.SERVER_IP: {'allow_post': True, 'allow_put': False,
                          'validate': {'type:ip_address': None},
                          'is_visible': True},
        const.SERVER_PORT: {'allow_post': True, 'allow_put': False,
                            'validate': {'type:range': [0, 65535]},
                            'convert_to': attr.convert_to_int,
                            'is_visible': True},
        const.WEIGHT: {'allow_post': True, 'allow_put': True,
                       'default': 1,
                       'validate': {'type:range': [0, 256]},
                       'convert_to': attr.convert_to_int,
                       'is_visible': True},
        const.ADMIN_STATE_UP: {'allow_post': True, 'allow_put': True,
                               'default': True,
                               'convert_to': attr.convert_to_boolean,
                               'is_visible': True},
        'ipvs_loadbalancer_id': {'allow_post': False, 'allow_put': False,
                                 'is_visible': True},
        'ipvs_virtualserver_id': {'allow_post': True, 'allow_put': False,
                                  'validate': {'type:uuid': None},
                                  'is_visible': True},
        const.DELAY: {'allow_post': True, 'allow_put': True,
                      'validate': {'type:non_negative': None},
                      'convert_to': attr.convert_to_int,
                      'is_visible': True},
        const.TIMEOUT: {'allow_post': True, 'allow_put': True,
                        'validate': {'type:non_negative': None},
                        'convert_to': attr.convert_to_int,
                        'is_visible': True},
        const.MAX_RETRIES: {'allow_post': True, 'allow_put': True,
                            'validate': {'type:range': [1, 10]},
                            'convert_to': attr.convert_to_int,
                            'is_visible': True},
    },
    const.IPVS_QUOTAS: {
        'tenant_id': {'allow_post': True, 'allow_put': False,
                      'validate': {'type:not_empty_string':
                                   attr.TENANT_ID_MAX_LEN},
                      'required_by_policy': True,
                      'is_visible': True},
        const.TARGET_TENANT: {'allow_post': True, 'allow_put': False,
                              'validate': {'type:uuid_default_or_none': None},
                              'is_visible': True, 'default': None},
        const.QUOTA: {'allow_post': True, 'allow_put': False,
                      'default': 0,
                      'validate': {'type:range': [-1, 256]},
                      'convert_to': attr.convert_to_int,
                      'is_visible': True},
        const.QUOTA_TYPE: {'allow_post': True, 'allow_put': False,
                           'validate': {'type:values': RESOURCE_TYPES},
                           'is_visible': True},
        const.QUOTA_USAGE: {'allow_post': False, 'allow_put': False,
                            'is_visible': True},
    },
}


class Networkingipvs(extensions.ExtensionDescriptor):

    @classmethod
    def get_name(cls):
        return "Networking IPVS service"

    @classmethod
    def get_alias(cls):
        return "networking_ipvs"

    @classmethod
    def get_description(cls):
        return "Extension for networking IPVS service"

    @classmethod
    def get_updated(cls):
        return "2018-02-27T10:00:00-00:00"

    @classmethod
    def get_resources(cls):
        plural_mappings = resource_helper.build_plural_mappings(
            {}, RESOURCE_ATTRIBUTE_MAP)
        attr.PLURALS.update(plural_mappings)
        return resource_helper.build_resource_info(
            plural_mappings, RESOURCE_ATTRIBUTE_MAP,
            const.NETWORKING_IPVS, translate_name=True)

    @classmethod
    def get_plugin_interface(cls):
        return NetworkingIPVSPluginBase

    def update_attributes_map(self, attributes, extension_attrs_map=None):
        super(Networkingipvs, self).update_attributes_map(
            attributes, extension_attrs_map=RESOURCE_ATTRIBUTE_MAP)

    def get_extended_resources(self, version):
        if version == "2.0":
            return RESOURCE_ATTRIBUTE_MAP
        else:
            return {}


@six.add_metaclass(abc.ABCMeta)
class NetworkingIPVSPluginBase(service_base.ServicePluginBase):

    def get_plugin_name(self):
        return const.NETWORKING_IPVS

    def get_plugin_type(self):
        return const.NETWORKING_IPVS

    def get_plugin_description(self):
        return 'Networking IPVS plugin'

    @property
    def _core_plugin(self):
        return manager.NeutronManager.get_plugin()

    @abc.abstractmethod
    def get_ipvs_loadbalancers(self, context, filters=None, fields=None):
        pass

    @abc.abstractmethod
    def get_ipvs_loadbalancer(self, context, id, fields=None):
        pass

    @abc.abstractmethod
    def create_ipvs_loadbalancer(self, context, loadbalancer):
        pass

    @abc.abstractmethod
    def update_ipvs_loadbalancer(self, context, id, loadbalancer):
        pass

    @abc.abstractmethod
    def delete_ipvs_loadbalancer(self, context, id):
        pass

    @abc.abstractmethod
    def create_ipvs_virtualserver(self, context, virtualserver):
        pass

    @abc.abstractmethod
    def get_ipvs_virtualserver(self, context, id, fields=None):
        pass

    @abc.abstractmethod
    def get_ipvs_virtualservers(self, context, filters=None, fields=None):
        pass

    @abc.abstractmethod
    def update_ipvs_virtualserver(self, context, id, virtualserver):
        pass

    @abc.abstractmethod
    def delete_ipvs_virtualserver(self, context, id):
        pass

    @abc.abstractmethod
    def create_ipvs_realserver(self, context, realserver):
        pass

    @abc.abstractmethod
    def get_ipvs_realserver(self, context, id, fields=None):
        pass

    @abc.abstractmethod
    def get_ipvs_realservers(self, context, filters=None, fields=None):
        pass

    @abc.abstractmethod
    def update_ipvs_realserver(self, context, id, realserver):
        pass

    @abc.abstractmethod
    def delete_ipvs_realserver(self, context, id):
        pass

    @abc.abstractmethod
    def create_ipvs_quota(self, context, ipvs_quota):
        pass

    @abc.abstractmethod
    def get_ipvs_quotas(self, context, filters=None, fields=None):
        pass
