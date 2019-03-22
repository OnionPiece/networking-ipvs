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

from neutron.api.v2 import attributes as attrs

from networking_ipvs.common import constants as const


def get_port_for_virtualserver(context, core_plugin, data):
    port = None
    if data.get(const.LISTEN_IP):
        ports = core_plugin.get_ports(
            context,
            filters={'network_id': [data['neutron_network_id']],
                     'fixed_ips': {'ip_address': [data[const.LISTEN_IP]]}})
        if ports:
            port = ports[0]
    if not port:
        req = compose_create_port_request(data)
        port = core_plugin.create_port(context, req)
    return {const.LISTEN_IP: port['fixed_ips'][0]['ip_address'],
            'neutron_port_id': port['id']}


def compose_create_port_request(data):
    req = {'port': {
        'tenant_id': data['tenant_id'],
        'network_id': data['neutron_network_id'],
        'device_owner': const.IPVS_PORT_DEVICE_OWNER,
        'device_id': data['ipvs_loadbalancer_id'],
        'name': '',
        const.ADMIN_STATE_UP: True,
        'mac_address': attrs.ATTR_NOT_SPECIFIED,
    }}
    if data.get(const.LISTEN_IP):
        req['port']['fixed_ips'] = [{"ip_address": data[const.LISTEN_IP]}]
    else:
        req['port']['fixed_ips'] = attrs.ATTR_NOT_SPECIFIED
    return req


def proto_to_num(proto):
    return int(proto) if proto.isdigit() else socket.getservbyname(proto)


def scheduler_format(data):
    if isinstance(data, dict):
        if const.SCHEDULER in data:
            data[const.SCHEDULER] = const.SCHEDULER_MAP.get(
                data[const.SCHEDULER])
    else:
        for d in data:
            if const.SCHEDULER in d:
                d[const.SCHEDULER] = const.SCHEDULER_MAP.get(
                    d[const.SCHEDULER])
