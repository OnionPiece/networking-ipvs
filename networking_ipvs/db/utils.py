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

from networking_ipvs.common import constants as const
from networking_ipvs.common import utils


def compose_vs_revision_extra(data):
    return '%(lip)s%(ip_sep)s%(lport)s%(vs_sep)s%(sip)s%(ip_sep)s%(sport)s' % {
        'lip': data.listen_ip, 'lport': data.listen_port,
        'ip_sep': const.EXTRA_IP_SEP, 'vs_sep': const.EXTRA_VS_SEP,
        'sip': '', 'sport': ''}


def compose_rs_revision_extra(data):
    return '%(lip)s%(ip_sep)s%(lport)s%(vs_sep)s%(sip)s%(ip_sep)s%(sport)s' % {
        'lip': data.ipvs_virtualserver.listen_ip,
        'lport': data.ipvs_virtualserver.listen_port,
        'ip_sep': const.EXTRA_IP_SEP, 'vs_sep': const.EXTRA_VS_SEP,
        'sip': data.server_ip, 'sport': data.server_port}


def get_subresource_keys(resource_type, db_inst, with_extra=True):
    vs_keys, rs_keys = {}, {}
    if resource_type == const.IPVS_LOADBALANCER:
        for vs_inst in db_inst.virtual_servers:
            vs_keys[vs_inst.id] = compose_vs_revision_extra(
                vs_inst) if with_extra else None
            rs_keys.update({
                rs_inst.id: compose_rs_revision_extra(
                    rs_inst) if with_extra else None
                for rs_inst in vs_inst.real_servers})
    elif resource_type == const.IPVS_VIRTUALSERVER:
        rs_keys = {
            rs_inst.id: compose_rs_revision_extra(
                rs_inst) if with_extra else None
            for rs_inst in db_inst.real_servers}
    return vs_keys, rs_keys
