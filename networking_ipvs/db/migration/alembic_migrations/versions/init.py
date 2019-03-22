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
#

from alembic import op
import sqlalchemy as sa

from networking_ipvs.common import constants as const


"""networking ipvs api

Revision ID: init
Revises: None
Create Date: 2018-02-27 10:50:15.606420

"""

revision = 'init'
down_revision = None


schedulers = sa.Enum(*const.DB_SUPPORTED_SCHEDULERS)
forward_methods = sa.Enum(*const.SUPPORTED_FORWARD_METHODS)
resource_types = sa.Enum(*const.SUPPORTED_RESOURCE_TYPES)


def upgrade():
    op.create_table(
        u'ipvs_loadbalancers',
        sa.Column(u'tenant_id', sa.String(255), nullable=False),
        sa.Column(u'id', sa.String(36), nullable=False, primary_key=True),
        sa.Column(u'name', sa.String(255), nullable=True),
        sa.Column(u'description', sa.String(255), nullable=True),
        sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),
    )

    op.create_table(
        u'ipvs_virtualservers',
        sa.Column(u'tenant_id', sa.String(255), nullable=False),
        sa.Column(u'id', sa.String(36), nullable=False, primary_key=True),
        sa.Column(u'name', sa.String(255), nullable=True),
        sa.Column(u'listen_ip', sa.String(64), nullable=False),
        sa.Column(u'listen_port', sa.Integer(), nullable=False),
        sa.Column(u'ipvs_loadbalancer_id', sa.String(36), nullable=False),
        sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint([u'ipvs_loadbalancer_id'],
                                [u'ipvs_loadbalancers.id'],
                                ondelete='CASCADE'),
        sa.Column(u'neutron_network_id', sa.String(36), nullable=False),
        sa.Column(u'neutron_port_id', sa.String(36), nullable=False),
        sa.Column(u'scheduler', schedulers, nullable=False),
        sa.Column(u'forward_method', forward_methods, nullable=False),
        sa.UniqueConstraint('listen_ip', 'listen_port', 'neutron_network_id'),
    )

    op.create_table(
        u'ipvs_realservers',
        sa.Column(u'tenant_id', sa.String(255), nullable=False),
        sa.Column(u'id', sa.String(36), nullable=False, primary_key=True),
        sa.Column(u'name', sa.String(255), nullable=True),
        sa.Column(u'server_ip', sa.String(64), nullable=False),
        sa.Column(u'server_port', sa.Integer(), nullable=False),
        sa.Column(u'weight', sa.Integer(), nullable=False),
        sa.Column(u'delay', sa.Integer(), nullable=False),
        sa.Column(u'timeout', sa.Integer(), nullable=False),
        sa.Column(u'max_retries', sa.Integer(), nullable=False),
        sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),
        sa.Column(u'ipvs_virtualserver_id', sa.String(36), nullable=False),
        sa.ForeignKeyConstraint([u'ipvs_virtualserver_id'],
                                [u'ipvs_virtualservers.id'],
                                ondelete='CASCADE'),
        sa.UniqueConstraint('server_ip', 'server_port',
                            'ipvs_virtualserver_id'),
    )

    op.create_table(
        u'ipvs_revisions',
        sa.Column(u'id', sa.String(36), primary_key=True),
        sa.Column(u'resource_type', resource_types, nullable=False),
        sa.Column(u'parent_id', sa.String(36)),
        sa.Column(u'created_at', sa.DateTime()),
        sa.Column(u'updated_at', sa.DateTime()),
        sa.Column(u'deleted_at', sa.DateTime()),
        sa.Column(u'extra', sa.String(128)),
    )
