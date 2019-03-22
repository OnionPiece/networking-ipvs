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

import hashlib
import sqlalchemy as sa
from sqlalchemy.orm import exc
from sqlalchemy.sql import expression as expr

from neutron.db import common_db_mixin
from oslo_log import log as logging
from oslo_utils import timeutils

from networking_ipvs.common import constants as const
from networking_ipvs.common import exceptions as ipvs_exc
from networking_ipvs.common import template
from networking_ipvs.common import utils
from networking_ipvs.db import models
from networking_ipvs.db import utils as dbutil


LOG = logging.getLogger(__name__)


Revision = models.Revision
TEMPLATE = None
ACTION_TO_TS = {const.CREATE: 'created_at',
                const.UPDATE: 'updated_at',
                const.DELETE: 'deleted_at'}


class RevisionDbMixin(common_db_mixin.CommonDbMixin):

    def get_revisions(self, context, start, end):
        # Loadbalancer updating and deletion can reflect to virtualserver
        # operations, so no need to send loadbalancer revisions
        filters = Revision.resource_type.in_([
            const.IPVS_VIRTUALSERVER, const.IPVS_REALSERVER])
        # c: created_at, u: updated_at, d: deleted_at, s:start, \:no
        # timeline             notify
        # s -- c -- u -- d       N
        # s -- c -- \u --d       N
        # s -- c -- u -- \d      Y
        # s -- c -- \u -- \d     Y
        # c -- s -- u -- d       Y
        # c -- s -- \u -- d      Y
        # c -- s -- u -- \d      Y
        # c -- s -- \u -- \d     N
        # c -- u -- s -- d       Y
        # c -- \u -- s -- d      Y
        # c -- u -- s -- \d      N
        # c -- \u -- s -- \d     N
        # c -- u -- d -- s       N
        # c -- \u -- d -- s      N
        # c -- u -- \d -- s      N
        # c -- \u -- \d -- s     N
        if start:
            filters = sa.and_(
                filters,
                sa.or_(sa.and_(Revision.created_at >= start,
                               Revision.deleted_at == expr.null()),
                       sa.and_(Revision.created_at <= start,
                               sa.or_(Revision.updated_at >= start,
                                      Revision.deleted_at >= start))))
        else:
            # special case for created_at > start
            filters = sa.and_(
                filters, sa.and_(Revision.deleted_at == expr.null()))
        if end:
            filters = sa.and_(
                filters,
                sa.or_(Revision.created_at <= end,
                       Revision.updated_at <= end,
                       Revision.deleted_at <= end))

        with context.session.begin(subtransactions=True):
            revisions = self._model_query(context, Revision).filter(filters)
        return [(str(rev.created_at), str(rev.updated_at or ''),
                 str(rev.deleted_at or ''), rev.id, rev.resource_type,
                 rev.parent_id, rev.extra)
                for rev in revisions]

    def _get_revision(self, context, id):
        try:
            revision = self._get_by_id(context, Revision, id)
        except exc.NoResultFound:
            raise ipvs_exc.ResourceNotFound(
                resource_kind=Revision.__table__.name, id=id)
        return revision

    def _get_timestamp(self, context, id, action=None):
        rev = self._get_revision(context, id)
        if action:
            return rev[ACTION_TO_TS[action]]
        elif rev.deleted_at:
            return str(rev.deleted_at)
        elif rev.updated_at:
            return str(rev.updated_at)
        else:
            return str(rev.created_at)

    def _get_notify_revisions(self, context, resource, res_id, res_dict):
        if resource == const.IPVS_LOADBALANCER:
            with context.session.begin(subtransactions=True):
                revisions = self._model_query(context, Revision).filter(
                    Revision.parent_id == res_id)
            for rev in revisions:
                res_dict[const.VIRTUALSERVERS][rev.id].update({
                    const.MD5: rev.extra})
            res_dict[const.TIMESTAMP] = self._get_timestamp(
                context, res_id, const.UPDATE)
        elif resource == const.IPVS_VIRTUALSERVER:
            rev = self._get_revision(context, res_id)
            res_dict.update({
                const.TIMESTAMP: str(rev.updated_at),
                const.MD5: rev.extra})
        else:
            parent_id = res_dict.pop('ipvs_virtualserver_id')
            rev = self._get_revision(context, parent_id)
            res_dict.update({
                const.TIMESTAMP: self._get_timestamp(context, res_id),
                const.MD5: rev.extra})

    def _get_revision_extra_for_deletion(self, resource_type, db_inst):
        if resource_type == const.IPVS_VIRTUALSERVER:
            return dbutil.compose_vs_revision_extra(db_inst)
        elif resource_type == const.IPVS_REALSERVER:
            return dbutil.compose_rs_revision_extra(db_inst)

    def _update_virtualserver_md5(self, context, vs_db_inst):
        conf_data = TEMPLATE.get_virtualserver_conf(
            {k: vs_db_inst[k] for k in (const.LISTEN_IP, const.LISTEN_PORT,
                                        const.ADMIN_STATE_UP, const.SCHEDULER,
                                        const.FORWARD_METHOD)},
            vs_db_inst.real_servers)
        md5 = hashlib.md5(conf_data).hexdigest()
        with context.session.begin(subtransactions=True):
            revision = self._get_revision(context, vs_db_inst.id)
            revision.update({const.EXTRA: md5})

    def _update_revisions_md5(self, context, resource_type, db_inst):
        global TEMPLATE
        if not TEMPLATE:
            TEMPLATE = template.VirtualServerTemplate()
        if resource_type == const.IPVS_LOADBALANCER:
            for vs_inst in db_inst.virtual_servers:
                self._update_virtualserver_md5(context, vs_inst)
        elif resource_type == const.IPVS_VIRTUALSERVER:
            self._update_virtualserver_md5(context, db_inst)
        elif resource_type == const.IPVS_REALSERVER:
            self._update_virtualserver_md5(context, db_inst.ipvs_virtualserver)

    def _update_revisions(self, context, id, resource_type, action,
                          parent_id=None, sub_vs_keys=None,
                          sub_rs_keys=None, extra=None):
        now = timeutils.utcnow()
        ts_attr = ACTION_TO_TS[action]

        def _get_bulk_updates(keys):
            if isinstance(keys, dict):
                return [{const.ID: _id, ts_attr: now, const.EXTRA: _extra}
                        for _id, _extra in keys.iteritems()]
            else:
                return [{const.ID: _id, ts_attr: now} for _id in keys]

        if action == const.CREATE:
            with context.session.begin(subtransactions=True):
                revision = Revision(id=id, resource_type=resource_type)
                if parent_id:
                    revision.parent_id = parent_id
                revision[ts_attr] = now
                context.session.add(revision)
        else:
            bulk_update = []
            if sub_vs_keys:
                bulk_update.extend(_get_bulk_updates(sub_vs_keys))
            if sub_rs_keys:
                bulk_update.extend(_get_bulk_updates(sub_rs_keys))
            with context.session.begin(subtransactions=True):
                rev = self._get_revision(context, id)
                rev.update({ts_attr: now})
                if extra:
                    rev.update({const.EXTRA: extra})
                if bulk_update:
                    context.session.bulk_update_mappings(Revision, bulk_update)
