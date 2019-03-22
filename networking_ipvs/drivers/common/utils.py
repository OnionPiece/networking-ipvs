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


def os_support_fullnat(executor):
    ipvsadm_help_output = executor([
        'sh', '-c', 'ipvsadm --help | grep fullnat'], extra_ok_codes=[1])
    return True if ipvsadm_help_output else False


def init_sync_daemon(sync_daemon_nic, sync_daemon_ids, executor):
    if not (sync_daemon_nic and sync_daemon_ids):
        return

    try:
        master_id, slave_ids = sync_daemon_ids.split(':')
        master_id = int(master_id)
        slave_ids = [int(sid) for sid in slave_ids.split(',')]
    except ValueError:
        return

    executor(['ipvsadm', '--stop-daemon', 'master'])
    executor(['ipvsadm', '--stop-daemon', 'backup'])
    executor([
        'ipvsadm', '--start-daemon', 'master', '--mcast-interface',
        sync_daemon_nic, '--syncid', master_id])
    for i in slave_ids:
        executor([
            'ipvsadm', '--start-daemon', 'backup', '--mcast-interface',
            sync_daemon_nic, '--syncid', i])
