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
from sqlalchemy import orm

from neutron.api.v2 import attributes as attr
from neutron.db import model_base
from neutron.db import models_v2

from networking_ipvs.common import constants as const


ORM_KEYS = ('ipvs_loadbalancer', const.VIRTUALSERVERS,
            'ipvs_virtualserver', const.REALSERVERS)


class LoadBalancer(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):

    __tablename__ = "ipvs_loadbalancers"

    name = sa.Column(sa.String(255))
    description = sa.Column(sa.String(255))
    admin_state_up = sa.Column(sa.Boolean(), nullable=False)


class VirtualServer(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):

    __tablename__ = "ipvs_virtualservers"

    name = sa.Column(sa.String(255))
    listen_ip = sa.Column(sa.String(64), nullable=False)
    listen_port = sa.Column(sa.Integer, nullable=False)
    neutron_network_id = sa.Column(sa.String(36), sa.ForeignKey('networks.id'))
    neutron_port_id = sa.Column(sa.String(36), sa.ForeignKey('ports.id'))
    neutron_port = orm.relationship(models_v2.Port)
    admin_state_up = sa.Column(sa.Boolean(), nullable=False)
    scheduler = sa.Column(sa.Enum(*const.SUPPORTED_SCHEDULERS), nullable=False)
    forward_method = sa.Column(sa.Enum(*const.SUPPORTED_FORWARD_METHODS),
                               nullable=False)
    ipvs_loadbalancer_id = sa.Column(
        sa.String(36),
        sa.ForeignKey("ipvs_loadbalancers.id", ondelete="CASCADE"),
        nullable=False)
    ipvs_loadbalancer = orm.relationship(
        LoadBalancer,
        backref=orm.backref(const.VIRTUALSERVERS, lazy='joined',
                            cascade='all,delete'))


class RealServer(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):

    __tablename__ = "ipvs_realservers"

    name = sa.Column(sa.String(255))
    server_ip = sa.Column(sa.String(64), nullable=False)
    server_port = sa.Column(sa.Integer, nullable=False)
    weight = sa.Column(sa.Integer, nullable=False)
    delay = sa.Column(sa.Integer, nullable=False)
    timeout = sa.Column(sa.Integer, nullable=False)
    max_retries = sa.Column(sa.Integer, nullable=False)
    admin_state_up = sa.Column(sa.Boolean(), nullable=False)
    ipvs_virtualserver_id = sa.Column(
        sa.String(36),
        sa.ForeignKey('ipvs_virtualservers.id', ondelete="CASCADE"),
        nullable=False)
    ipvs_virtualserver = orm.relationship(
        VirtualServer,
        backref=orm.backref(const.REALSERVERS, lazy='joined',
                            cascade='all,delete'))


class Revision(model_base.BASEV2, models_v2.HasId):

    __tablename__ = "ipvs_revisions"
    resource_type = sa.Column(sa.Enum(*const.SUPPORTED_RESOURCE_TYPES),
                              nullable=False)
    parent_id = sa.Column(sa.String(36))
    created_at = sa.Column(sa.DateTime())
    updated_at = sa.Column(sa.DateTime())
    deleted_at = sa.Column(sa.DateTime())
    extra = sa.Column(sa.String(length=128))


class Quota(model_base.BASEV2):

    __tablename__ = "ipvs_quotas"
    tenant_id = sa.Column(sa.String(attr.TENANT_ID_MAX_LEN), primary_key=True)
    quota = sa.Column(sa.Integer, nullable=False)
    quota_type = sa.Column(sa.Enum(*const.SUPPORTED_RESOURCE_TYPES),
                           primary_key=True)
