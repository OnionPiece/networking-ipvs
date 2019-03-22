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

import sqlalchemy as sa

from oslo_log import log as logging

from networking_ipvs.common import constants as const
from networking_ipvs.db import models


LOG = logging.getLogger(__name__)


Quota = models.Quota
DEFAULT_LB_QUOTA = 10
DEFAULT_VS_QUOTA = 10
DEFAULT_RS_QUOTA = 100
UNSET = -2


class QuotaDbMixin(object):

    def _set_and_get_default_quotas(self, context):
        bulk_inserts = [
            {'tenant_id': 'default',
             const.QUOTA_TYPE: const.IPVS_LOADBALANCER,
             const.QUOTA: DEFAULT_LB_QUOTA},
            {'tenant_id': 'default',
             const.QUOTA_TYPE: const.IPVS_VIRTUALSERVER,
             const.QUOTA: DEFAULT_VS_QUOTA},
            {'tenant_id': 'default',
             const.QUOTA_TYPE: const.IPVS_REALSERVER,
             const.QUOTA: DEFAULT_RS_QUOTA}]
        with context.session.begin(subtransactions=True):
            context.session.bulk_insert_mappings(Quota, bulk_inserts)
            context.session.expire_all()
        return bulk_inserts

    def _get_quotas(self, context, filters):
        with context.session.begin(subtransactions=True):
            quotas = context.session.query(Quota)
        if 'tenant_id' in filters and context.is_admin:
            quotas = quotas.filter(
                Quota.tenant_id.in_(['default', filters['tenant_id']]))
        else:
            quotas = quotas.filter(
                Quota.tenant_id.in_(['default', context.tenant_id]))
        all_quotas = quotas.all()
        if not all_quotas:
            all_quotas = self._set_and_get_default_quotas(context)
        type_filter = filters.get(
            const.QUOTA_TYPE,
            [const.IPVS_LOADBALANCER, const.IPVS_VIRTUALSERVER,
             const.IPVS_REALSERVER])
        default_ones = []
        ret = []
        for q in all_quotas:
            if q[const.QUOTA_TYPE] not in type_filter:
                continue
            qdict = {'tenant_id': q['tenant_id'],
                     const.QUOTA: q[const.QUOTA],
                     const.QUOTA_TYPE: q[const.QUOTA_TYPE]}
            if q['tenant_id'] == 'default':
                default_ones.append(qdict)
            else:
                ret.append(qdict)
        custom = [q[const.QUOTA_TYPE] for q in ret]
        for q in default_ones:
            if q[const.QUOTA_TYPE] not in custom:
                q['tenant_id'] = context.tenant_id
                ret.append(q)
        return ret

    def get_quotas(self, context, filters=None, fields=None):
        return self._get_quotas(context, filters or {})

    def set_quota(self, context, quota):
        if not context.is_admin:
            raise ipvs_exc.OnlyAdminCanSetOtherTenantQuota()
        data = quota[const.IPVS_QUOTA]
        target_tenant = data.pop(const.TARGET_TENANT, None)
        tenant_id = target_tenant or context.tenant_id
        quota_type = data[const.QUOTA_TYPE]
        quota = data[const.QUOTA]
        with context.session.begin(subtransactions=True):
            qry = context.session.query(Quota).filter(
                Quota.tenant_id == tenant_id,
                Quota.quota_type == quota_type).all()
            if qry:
                qry = qry[0]
                if quota == UNSET:
                    context.session.delete(qry)
                else:
                    qry.update({const.QUOTA: quota})
            elif quota != UNSET:
                context.session.add(Quota(tenant_id=tenant_id,
                                          quota_type=quota_type,
                                          quota=quota))
        data['tenant_id'] = tenant_id
        return data
