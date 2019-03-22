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

from neutron_lib import constants as lib_const


DEVICE_DRIVER = 'device_driver'

NETWORKING_IPVS = 'NETWORKING_IPVS'

IPVS_LOADBALANCER = 'ipvs_loadbalancer'
IPVS_VIRTUALSERVER = 'ipvs_virtualserver'
IPVS_REALSERVER = 'ipvs_realserver'
IPVS_QUOTA = 'ipvs_quota'
SUPPORTED_RESOURCE_TYPES = (IPVS_LOADBALANCER, IPVS_VIRTUALSERVER,
                            IPVS_REALSERVER)

IPVS_LOADBALANCERS = 'ipvs_loadbalancers'
IPVS_VIRTUALSERVERS = 'ipvs_virtualservers'
IPVS_REALSERVERS = 'ipvs_realservers'
IPVS_QUOTAS = 'ipvs_quotas'

CREATE = 'create'
UPDATE = 'update'
DELETE = 'delete'
SUPPORTED_ACTIONS = (CREATE, UPDATE, DELETE)

NETWORKING_IPVS_AGENT_TYPE = 'Networking-IPVS agent'
NETWORKING_IPVS_PLUGIN = 'n-ipvs-plugin'
NETWORKING_IPVS_AGENT = 'n-ipvs_agent'

IPVS = 'ipvs'
IPVS_FULLNAT = 'ipvs:fullnat'

IPVS_PORT_DEVICE_OWNER = (
    lib_const.DEVICE_OWNER_NETWORK_PREFIX + 'IPVS_LOADBALANCER')

ID = 'id'
EXTRA = 'extra'
MD5 = 'md5'
TIMESTAMP = 'timestamp'
WHAT_CHANGED = 'what_changed'
SCHEDULER = 'scheduler'
LISTEN_IP = 'listen_ip'
LISTEN_PORT = 'listen_port'
SERVER_IP = 'server_ip'
SERVER_PORT = 'server_port'
ADMIN_STATE_UP = 'admin_state_up'
WEIGHT = 'weight'
DELAY = 'delay'
TIMEOUT = 'timeout'
MAX_RETRIES = 'max_retries'
FORWARD_METHOD = 'forward_method'
LOADBALANCER_NOTIFY_KEYS = [ADMIN_STATE_UP]
VIRTUALSERVER_NOTIFY_KEYS = [SCHEDULER, ADMIN_STATE_UP, FORWARD_METHOD]
REALSERVER_NOTIFY_KEYS = [WEIGHT, DELAY, TIMEOUT, MAX_RETRIES, ADMIN_STATE_UP]
NOTIFY_KEY_MAP = {IPVS_LOADBALANCER: LOADBALANCER_NOTIFY_KEYS,
                  IPVS_VIRTUALSERVER: VIRTUALSERVER_NOTIFY_KEYS,
                  IPVS_REALSERVER: REALSERVER_NOTIFY_KEYS}
REALSERVERS = 'real_servers'
VIRTUALSERVER = 'virtualserver'
VIRTUALSERVERS = 'virtual_servers'
LB_ADMIN = 'lb_admin_state'
QUOTA = 'quota'
QUOTA_TYPE = 'quota_type'
QUOTA_USAGE = 'quota_usage'
TARGET_TENANT = 'target_tenant'

ROUND_ROBIN = 'ROUND_ROBIN'
LEAST_CONNECTIONS = 'LEAST_CONNECTIONS'
SOURCE_IP = 'SOURCE_IP'
SUPPORTED_SCHEDULERS = (LEAST_CONNECTIONS, ROUND_ROBIN, SOURCE_IP)
IPVS_WEIGHTED_ROUND_ROBIN = 'wrr'
IPVS_WEIGHTED_LEAST_CONN = 'wlc'
IPVS_SOURCE_HASHING = 'sh'
DB_SUPPORTED_SCHEDULERS = (IPVS_WEIGHTED_ROUND_ROBIN, IPVS_WEIGHTED_LEAST_CONN,
                           IPVS_SOURCE_HASHING)
IPVS_SH_EXTRA = '-b sh-fallback'
SCHEDULER_MAP = {
    IPVS_WEIGHTED_ROUND_ROBIN: ROUND_ROBIN,
    IPVS_WEIGHTED_LEAST_CONN: LEAST_CONNECTIONS,
    IPVS_SOURCE_HASHING: SOURCE_IP,
    ROUND_ROBIN: IPVS_WEIGHTED_ROUND_ROBIN,
    LEAST_CONNECTIONS: IPVS_WEIGHTED_LEAST_CONN,
    SOURCE_IP: IPVS_SOURCE_HASHING
    }

TUN = 'TUN'
DR = 'DR'
NAT = 'NAT'
FULLNAT = 'FNAT'
SUPPORTED_FORWARD_METHODS = (TUN, DR, NAT, FULLNAT)
NORMAL_FORWARDS = (TUN, DR)

REAL_SERVER_INST_FMT = '%(server_ip)s:%(server_port)s'

DOWN = '.down'
EXTRA_IP_SEP = ':'
EXTRA_VS_SEP = '-'
ALL = 'all'
