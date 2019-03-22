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

"""add quotas

Revision ID: 7ed83f5168d
Revises: expand_init
Create Date: 2018-03-19 23:18:09.360427

"""

from alembic import op
import sqlalchemy as sa

from networking_ipvs.common import constants as const

revision = '7ed83f5168d'
down_revision = 'init'

resource_types = sa.Enum(*const.SUPPORTED_RESOURCE_TYPES)


def upgrade():
    op.create_table(
        'ipvs_quotas',
        sa.Column('tenant_id', sa.String(255), primary_key=True),
        sa.Column('quota', sa.Integer(), nullable=False),
        sa.Column('quota_type', resource_types, primary_key=True),
    )
