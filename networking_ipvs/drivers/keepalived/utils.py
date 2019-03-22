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

from networking_ipvs.common import constants as const


def parse_virtualserver_conf(file_path):
    vs = {}
    state = 'expect_vs'
    vs_attrs = {'lb_algo': const.SCHEDULER,
                'lb_kind': const.FORWARD_METHOD}
    rs_attrs = {'!id': 'id',
                'weight': const.WEIGHT,
                'connect_timeout': const.TIMEOUT,
                'retry': const.MAX_RETRIES,
                'delay_before_retry': const.DELAY}
    rs_key = ''
    with open(file_path) as f:
        for line in f:
            line = line.strip()
            if not line or line[:2] == '! ':
                continue
            fields = line.split()
            if state == 'expect_vs':
                if len(fields) == 4 and fields[0] == 'virtual_server' and (
                    netaddr.valid_ipv4(fields[1])) and (
                        fields[2].isdigit()) and fields[3] == '{':
                    vs[const.LISTEN_IP] = fields[1]
                    vs[const.LISTEN_PORT] = int(fields[2])
                    state = 'in_vs'
            elif state == 'in_vs':
                if fields[0] in vs_attrs:
                    vs[vs_attrs[fields[0]]] = fields[1]
                    if fields[0] == 'lb_kind':
                        state = 'expect_rs'
            elif state == 'expect_rs':
                if len(fields) == 4 and fields[0] == 'real_server' and (
                    netaddr.valid_ipv4(fields[1])) and (
                        fields[2].isdigit()) and fields[3] == '{':
                    server_ip = fields[1]
                    server_port = fields[2]
                    up = True
                    state = 'in_rs'
                elif len(fields) == 5 and fields[0] == '#' and (
                    fields[1] == 'real_server') and netaddr.valid_ipv4(
                        fields[2]) and fields[3].isdigit() and (
                            fields[4] == '{'):
                    server_ip = fields[2]
                    server_port = fields[3]
                    up = False
                    state = 'in_rs_down'
                else:
                    continue
                rs_key = '%s:%s' % (server_ip, server_port)
                if const.REALSERVERS not in vs:
                    vs[const.REALSERVERS] = {}
                vs[const.REALSERVERS][rs_key] = {}
                vs[const.REALSERVERS][rs_key][const.SERVER_IP] = server_ip
                vs[const.REALSERVERS][rs_key][const.SERVER_PORT] = server_port
                vs[const.REALSERVERS][rs_key][const.ADMIN_STATE_UP] = up
            elif state == 'in_rs':
                if fields[0] in rs_attrs:
                    attr = rs_attrs[fields[0]]
                    vs[const.REALSERVERS][rs_key][attr] = fields[1]
                    if fields[0] == 'delay_before_retry':
                        rs_key = ''
                        state = 'expect_rs'
            elif state == 'in_rs_down':
                if fields[0] == '#' and fields[1] in rs_attrs:
                    attr = rs_attrs[fields[1]]
                    vs[const.REALSERVERS][rs_key][attr] = fields[2]
                    if fields[1] == 'delay_before_retry':
                        rs_key = ''
                        state = 'expect_rs'
    if vs:
        vs[const.ADMIN_STATE_UP] = file_path.endswith(const.DOWN) ^ True
    return vs
