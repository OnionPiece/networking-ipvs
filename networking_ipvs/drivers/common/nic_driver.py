# Copyright 2018
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

import netaddr

from neutron.agent.linux import ip_lib
from neutron.agent.linux import utils
from oslo_log import log as logging

from networking_ipvs._i18n import _LE
from networking_ipvs.common import constants as const

LOG = logging.getLogger(__name__)


class NICDriver(object):

    def __init__(self, conf):
        self.conf = conf
        self._parse_nic_mapping()

    def _parse_nic_mapping(self):
        self._cidr_nic_mapping = {}
        for cidr_to_nic in self.conf.ipvs.ipvs_vip_nic_mapping.split(','):
            cidr, nic = cidr_to_nic.split(':')
            self._cidr_nic_mapping[cidr] = nic
        for cidr in self._cidr_nic_mapping:
            self._cidr_nic_mapping[cidr] = ip_lib.IPDevice(
                self._cidr_nic_mapping[cidr])
        self._cidr_nic_mapping['default'] = self._cidr_nic_mapping.get(
            '*', self._cidr_nic_mapping.values()[0])

    def check_nic_vips(self, deployed_vips):
        current_nic_vips = [
            addr['cidr'][:-3]
            for nic in self._cidr_nic_mapping.values()
            for addr in nic.addr.list()
            if addr['cidr'][-3:] == '/32']
        for vip in set(deployed_vips) - set(current_nic_vips):
            self.try_plug_vip(vip)
        for vip in set(current_nic_vips) - set(deployed_vips):
            self.try_unplug_vip(vip)

    def try_plug_vip(self, vip_address):
        try:
            self._get_nic_for_vip(vip_address).addr.add(vip_address + '/32')
        except RuntimeError as e:
            if 'RTNETLINK answers: File exists' not in e.message:
                msg = _LE("Failed to plug vip for address %s") % vip_address
                LOG.error(msg)

    def try_unplug_vip(self, vip_address):
        try:
            self._get_nic_for_vip(vip_address).addr.delete(vip_address + '/32')
        except RuntimeError as e:
            if 'Cannot assign requested address' not in e.message:
                msg = _LE("Failed to unplug vip for address %s") % vip_address
                LOG.error(msg)

    def _get_nic_for_vip(self, vip_address):
        for cidr in self._cidr_nic_mapping:
            if cidr in ('*', 'default'):
                continue
            if netaddr.IPAddress(vip_address) in netaddr.IPNetwork(cidr):
                _vip_nic = self._cidr_nic_mapping[cidr]
                break
        else:
            _vip_nic = self._cidr_nic_mapping['default']
        return _vip_nic
