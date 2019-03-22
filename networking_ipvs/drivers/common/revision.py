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

import os
import time

from neutron import context as ncontext
from oslo_log import log as logging

from networking_ipvs.common import constants as const
from networking_ipvs.common import exceptions as ipvs_exc
from networking_ipvs.common import utils


LOG = logging.getLogger(__name__)


class RevisionHelper(object):

    def __init__(self, conf, plugin_rpc, delete_callback, update_callback):
        self.conf = conf
        self.context = ncontext.get_admin_context_without_session()
        self.plugin_rpc = plugin_rpc
        self.delete_callback = delete_callback
        self.update_callback = update_callback

    def _get_local_revision(self):
        revision = None
        if os.path.exists(self.conf.revision.revision_path):
            with open(self.conf.revision.revision_path) as f:
                revision = f.read().strip()
        return revision

    def _set_local_revision(self, new_revision):
        with open(self.conf.revision.revision_path, 'w+') as f:
            f.write(new_revision)

    def _get_upstream_revisions(self, start=None, end=None):
        if not start:
            start = self._get_local_revision()
        return self.plugin_rpc.get_revisions(start, end)

    def update(self, vs_info, realservers):
        if realservers:
            new_revision = max([rs[const.TIMESTAMP] for rs in realservers])
        else:
            new_revision = vs_info[const.TIMESTAMP]
        missed_revisions = self._get_upstream_revisions(end=new_revision)
        if missed_revisions:
            new_revision = self._process_revisions(missed_revisions)
        self._set_local_revision(new_revision)

    def update_with_upstream(self, start=None, end=None):
        missed_revisions = self._get_upstream_revisions(start, end)
        if missed_revisions:
            new_revision = self._process_revisions(missed_revisions)
            if not end and new_revision:
                self._set_local_revision(new_revision)
            elif end:
                self._set_local_revision(end)

    def _filter_revisions(self, revisions):
        # all revisions we can get should with the following timelines:
        # (s: start, c: created_at, u: updated_at, d: deleted_at, \:non-)
        #             s -- c -- u -- \d
        #             s -- c -- \u -- \d
        #        c -- s -- u -- d
        #        c -- s -- \u -- d
        #        c -- s -- u -- \d
        #   c -- u -- s -- d
        #  c -- \u -- s -- d
        new_ts = 0
        to_delete = {}
        to_create_or_update = {const.IPVS_VIRTUALSERVER: set(),
                               const.IPVS_REALSERVER: {}}
        for (created_at, updated_at, deleted_at, res_id, res_type, parent_id,
             extra) in revisions:
            new_ts = max(new_ts, created_at, updated_at, deleted_at)
            if deleted_at:
                vs_key, rs = extra.split(const.EXTRA_VS_SEP)
                listen_ip, listen_port = vs_key.split(const.EXTRA_IP_SEP)
                if res_type == const.IPVS_VIRTUALSERVER:
                    if res_id not in to_delete:
                        to_delete[res_id] = {
                            const.LISTEN_IP: listen_ip,
                            const.LISTEN_PORT: listen_port}
                    else:
                        to_delete[res_id][const.REALSERVERS].clear()
                    to_delete[res_id][const.REALSERVERS] = {const.ALL: 1}
                else:
                    server_ip, server_port = rs.split(const.EXTRA_IP_SEP)
                    if parent_id not in to_delete:
                        to_delete[parent_id] = {
                            const.LISTEN_IP: listen_ip,
                            const.LISTEN_PORT: listen_port,
                            const.REALSERVERS: {
                                res_id: {
                                    const.SERVER_IP: server_ip,
                                    const.SERVER_PORT: server_port}}}
                    elif const.ALL not in to_delete[parent_id].get(
                            const.REALSERVERS):
                        to_delete[parent_id][const.REALSERVERS][res_id] = {
                            const.SERVER_IP: server_ip,
                            const.SERVER_PORT: server_port}
                continue

            if res_type == const.IPVS_VIRTUALSERVER and updated_at:
                to_create_or_update[res_type].add(res_id)
                continue

            if res_type == const.IPVS_REALSERVER and (
                const.ALL not in to_delete.get(parent_id, {}).get(
                    const.REALSERVERS, {})):
                if parent_id not in to_create_or_update[res_type]:
                    to_create_or_update[res_type][parent_id] = set()
                to_create_or_update[res_type][parent_id].add(res_id)
        to_create_or_update[const.IPVS_VIRTUALSERVER] -= set(
            to_create_or_update[const.IPVS_REALSERVER].keys())
        return new_ts, to_delete, to_create_or_update

    def _process_revisions(self, revisions):
        new_ts, to_delete, to_create_or_update = self._filter_revisions(
            revisions)
        if to_delete:
            for vs in to_delete.values():
                realservers = vs.pop(const.REALSERVERS)
                if const.ALL in realservers:
                    realservers = []
                else:
                    realservers = realservers.values()
                self.delete_callback(vs, realservers)
            # NOTE: In missed revisions, some virtual server with their real
            # servers may get re-created after deleted. In such a case,
            # deleting and creating the same vs & rs so close will case ipvs
            # "Memory allocation problem". Sleep 1 sec is a trick to avoid that
            time.sleep(1)
        for vid, rid in to_create_or_update[const.IPVS_REALSERVER].iteritems():
            realservers = self.plugin_rpc.get_ipvs_realservers(
                filters={'ipvs_virtualserver_id': [vid], 'id': rid})
            if not realservers:
                continue
            for rs in realservers:
                vs_info = rs.pop(const.VIRTUALSERVER)
            self.update_callback(vs_info, realservers)
        vids = to_create_or_update[const.IPVS_VIRTUALSERVER]
        if vids:
            for vs in self.plugin_rpc.get_ipvs_virtualservers(
                    filters={'id': vids}):
                self.update_callback(vs)
        return new_ts
