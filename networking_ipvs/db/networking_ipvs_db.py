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

from sqlalchemy.orm import exc

from neutron.callbacks import events
from neutron.callbacks import registry
from neutron.callbacks import resources
from oslo_db import exception as db_exc
from oslo_log import log as logging
from oslo_utils import timeutils
from oslo_utils import uuidutils

from networking_ipvs.common import constants as const
from networking_ipvs.common import utils
from networking_ipvs.common import exceptions as ipvs_exc
from networking_ipvs.db import models
from networking_ipvs.db import quotas
from networking_ipvs.db import revisions
from networking_ipvs.db import utils as dbutil
from networking_ipvs.extensions import networkingipvs as ipvs_ext


LOG = logging.getLogger(__name__)


class NetworkingIPVSPluginDb(ipvs_ext.NetworkingIPVSPluginBase,
                             revisions.RevisionDbMixin,
                             quotas.QuotaDbMixin):

    def _get_model(self, resource):
        return {
            const.IPVS_LOADBALANCER: models.LoadBalancer,
            const.IPVS_VIRTUALSERVER: models.VirtualServer,
            const.IPVS_REALSERVER: models.RealServer,
        }[resource]

    def _get_resource(self, context, model, id):
        try:
            resource = self._get_by_id(context, model, id)
        except exc.NoResultFound:
            raise ipvs_exc.ResourceNotFound(resource_kind=model.__table__.name,
                                            id=id)
        return resource

    def _make_resource_dict(self, resource, fields=None):
        res = {k: v for (k, v) in resource.items() if k not in models.ORM_KEYS}
        # all the following attrs are mainly used for resource notify
        if hasattr(resource, const.VIRTUALSERVERS):
            res[const.VIRTUALSERVERS] = [
                {const.ID: vs.id,
                 const.LISTEN_IP: vs.listen_ip,
                 const.LISTEN_PORT: vs.listen_port,
                 const.SCHEDULER: vs.scheduler,
                 const.FORWARD_METHOD: vs.forward_method,
                 const.ADMIN_STATE_UP: vs.admin_state_up,
                 'neutron_port_id': vs.neutron_port_id,
                 const.REALSERVERS: [
                     {const.ID: rs.id,
                      const.SERVER_IP: rs.server_ip,
                      const.SERVER_PORT: rs.server_port,
                      const.WEIGHT: rs.weight,
                      const.DELAY: rs.delay,
                      const.TIMEOUT: rs.timeout,
                      const.MAX_RETRIES: rs.max_retries,
                      const.ADMIN_STATE_UP: rs.admin_state_up}
                     for rs in vs.real_servers]}
                for vs in resource.virtual_servers]
        elif hasattr(resource, const.REALSERVERS):
            res[const.LB_ADMIN] = resource.ipvs_loadbalancer.admin_state_up
            res[const.REALSERVERS] = {
                rs.id: rs.admin_state_up for rs in resource.real_servers}
        elif hasattr(resource, 'ipvs_virtualserver_id'):
            res[const.LB_ADMIN] = (
                resource.ipvs_virtualserver.ipvs_loadbalancer.admin_state_up)
            res[const.VIRTUALSERVER] = {
                const.ID: resource.ipvs_virtualserver.id,
                const.LISTEN_IP: resource.ipvs_virtualserver.listen_ip,
                const.LISTEN_PORT: resource.ipvs_virtualserver.listen_port,
                const.SCHEDULER: resource.ipvs_virtualserver.scheduler,
                const.FORWARD_METHOD: (
                    resource.ipvs_virtualserver.forward_method),
                const.ADMIN_STATE_UP: (
                    resource.ipvs_virtualserver.admin_state_up)}
        return self._fields(res, fields)

    def _usage_check(self, context, resource, model):
        used = self._get_collection_count(context, model)
        quota = self.get_quotas(
            context, filters={const.QUOTA_TYPE: [resource]})[0][const.QUOTA]
        if used >= quota:
            raise ipvs_exc.QuotaExceed()

    def _db_create(self, context, resource):
        resource_type, data = resource.items()[0]
        model = self._get_model(resource_type)
        self._usage_check(context, resource_type, model)
        utils.scheduler_format(data)
        try:
            with context.session.begin(subtransactions=True):
                db_inst = model(
                    id=uuidutils.generate_uuid(),
                    **data)
                context.session.add(db_inst)
        except db_exc.DBDuplicateEntry:
            if resource_type == const.IPVS_VIRTUALSERVER:
                raise ipvs_exc.VirtualServerEntityExists(
                    listen_ip=data[const.LISTEN_IP],
                    listen_port=data[const.LISTEN_PORT],
                    neutron_network_id=data['neutron_network_id'])
            elif resource_type == const.IPVS_REALSERVER:
                raise ipvs_exc.RealServerEntityExists(
                    server_ip=data[const.SERVER_IP],
                    server_port=data[const.SERVER_PORT],
                    ipvs_virtualserver_id=data['ipvs_virtualserver_id'])
        inst_dict = self._make_resource_dict(db_inst)
        parent_id = inst_dict.get('ipvs_loadbalancer_id') or inst_dict.get(
            'ipvs_virtualserver_id')
        self._update_revisions(context, inst_dict[const.ID], resource_type,
                               const.CREATE, parent_id=parent_id)
        return inst_dict

    def _db_update(self, context, id, resource):
        resource_type, data = resource.items()[0]
        utils.scheduler_format(data)
        model = self._get_model(resource_type)
        with context.session.begin(subtransactions=True):
            db_inst = self._get_resource(context, model, id)
            before_change = self._make_resource_dict(db_inst)
            db_inst.update(data)
        db_inst = self._get_resource(context, model, id)
        after_change = self._make_resource_dict(db_inst)
        what_changed = [
            k for k in after_change
            if k in const.NOTIFY_KEY_MAP[resource_type] and (
                after_change[k] != before_change[k])]
        vs_ids, rs_ids = None, None
        if const.ADMIN_STATE_UP in what_changed and (
                resource_type != const.IPVS_REALSERVER):
            vs_keys, rs_keys = dbutil.get_subresource_keys(
                resource_type, db_inst, False)
            vs_ids, rs_ids = vs_keys.keys(), rs_keys.keys()
            if vs_ids or rs_ids:
                self._update_subresource_admin_state(
                    context, vs_ids, rs_ids, db_inst.admin_state_up)
            after_change = self._make_resource_dict(self._get_resource(
                context, model, id))
        if what_changed:
            after_change.update({const.WHAT_CHANGED: what_changed})
            self._update_revisions(context, id, resource_type, const.UPDATE,
                                   sub_vs_keys=vs_ids, sub_rs_keys=rs_ids)
        return after_change

    def _update_subresource_admin_state(self, context, vs_ids, rs_ids, up):
        vs_bulk_updating = [
            {const.ID: _id, const.ADMIN_STATE_UP: up} for _id in vs_ids]
        rs_bulk_updating = [
            {const.ID: _id, const.ADMIN_STATE_UP: up} for _id in rs_ids]
        with context.session.begin(subtransactions=True):
            if vs_bulk_updating:
                context.session.bulk_update_mappings(
                    models.VirtualServer, vs_bulk_updating)
            if rs_bulk_updating:
                context.session.bulk_update_mappings(
                    models.RealServer, rs_bulk_updating)
            context.session.expire_all()

    def _db_delete(self, context, resource_type, id, force=False):
        model = self._get_model(resource_type)
        db_inst = self._get_resource(context, model, id)
        vs_keys, rs_keys = dbutil.get_subresource_keys(resource_type, db_inst)
        if not force:
            if vs_keys or rs_keys:
                raise ipvs_exc.ResourceInUse(resource=resource_type, id=id)
        extra = self._get_revision_extra_for_deletion(resource_type, db_inst)
        inst_dict = self._make_resource_dict(db_inst)
        with context.session.begin(subtransactions=True):
            context.session.delete(db_inst)
        self._update_revisions(context, id, resource_type, const.DELETE,
                               sub_vs_keys=vs_keys, sub_rs_keys=rs_keys,
                               extra=extra)
        return inst_dict

    def _db_get(self, context, resource, id, fields=None):
        return self._make_resource_dict(
            self._get_resource(context, self._get_model(resource), id),
            fields)

    def _db_gets(self, context, resource, filters=None, fields=None,
                 sorts=None, limit=None, marker=None, page_reverse=False):
        marker_obj = self._get_marker_obj(context, resource, limit, marker)
        return self._get_collection(
            context, self._get_model(resource), self._make_resource_dict,
            filters=filters, fields=fields, sorts=sorts, limit=limit,
            marker_obj=marker_obj, page_reverse=page_reverse)

    def _db_get_usage(self, context, filters):
        resource_types = filters.pop(
            const.QUOTA_TYPE, [const.IPVS_LOADBALANCER, const.IPVS_REALSERVER,
                               const.IPVS_VIRTUALSERVER])
        return {res: self._get_collection_count(context, self._get_model(res),
                                                filters)
                for res in resource_types}

    def _update_revisions_md5(self, context, resource_type, id):
        model = self._get_model(resource_type)
        db_inst = self._get_resource(context, model, id)
        super(NetworkingIPVSPluginDb, self)._update_revisions_md5(
            context, resource_type, db_inst)
