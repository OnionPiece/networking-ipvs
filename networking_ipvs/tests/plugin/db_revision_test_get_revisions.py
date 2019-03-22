#!/usr/bin/python2.7

import datetime
import sqlalchemy as sa

from neutron import context as ncontext
from oslo_utils import timeutils
from oslo_utils import uuidutils

from networking_ipvs.common import constants as const
from networking_ipvs.db import models
from networking_ipvs.db import revisions


context = ncontext.get_admin_context()
resource_types = sa.Enum(*const.SUPPORTED_RESOURCE_TYPES)

# create table ipvs_revisions in context engine sqlite://
metadata = sa.MetaData()
sa.Table('ipvs_revisions', metadata,
         sa.Column('id', sa.String(36), primary_key=True),
         sa.Column('resource_type', resource_types, nullable=False),
         sa.Column('parent_id', sa.String(36)),
         sa.Column('created_at', sa.DateTime(), nullable=True),
         sa.Column('updated_at', sa.DateTime(), nullable=True),
         sa.Column('deleted_at', sa.DateTime(), nullable=True),
         sa.Column('extra', sa.String(128)))
metadata.create_all(context.session.get_bind())

# c: created_at, u: updated_at, d: deleted_at, s:start, \:no
cases = [
    # (notify, timeline)
    (False, 's -- c -- u -- d'),
    (False, 's -- c -- \u --d'),
    (True, 's -- c -- u -- \d'),
    (True, 's -- c -- \u -- \d'),
    #
    (True, 'c -- s -- u -- d'),
    (True, 'c -- s -- \u -- d'),
    (True, 'c -- s -- u -- \d'),
    (False, 'c -- s -- \u -- \d'),
    #
    (True, 'c -- u -- s -- d'),
    (True, 'c -- \u -- s -- d'),
    (False, 'c -- u -- s -- \d'),
    (False, 'c -- \u -- s -- \d'),
    #
    (False, 'c -- u -- d -- s'),
    (False, 'c -- \u -- d -- s'),
    (False, 'c -- u -- \d -- s'),
    (False, 'c -- \u -- \d -- s')]

valid_cases = [i for i in range(16) if cases[i][0]]

t_fmt = '%Y-%m-%d %H:%M:%S'
t_3 = datetime.datetime.strptime('2018-03-18 21:00:00', t_fmt)
t_2 = datetime.datetime.strptime('2018-03-18 22:00:00', t_fmt)
t_1 = datetime.datetime.strptime('2018-03-18 23:00:00', t_fmt)
t0 = datetime.datetime.strptime('2018-03-19 00:00:00', t_fmt)
t1 = datetime.datetime.strptime('2018-03-19 01:00:00', t_fmt)
t2 = datetime.datetime.strptime('2018-03-19 02:00:00', t_fmt)
t3 = datetime.datetime.strptime('2018-03-19 03:00:00', t_fmt)

cases_ts = [
    (t1, t2, t3),
    (t1, None, t3),
    (t1, t2, None),
    (t1, None, None),
    #
    (t_1, t1, t2),
    (t_1, None, t2),
    (t_1, t1, None),
    (t_1, None, None),
    #
    (t_2, t_1, t1),
    (t_2, None, t1),
    (t_2, t_1, None),
    (t_2, None, None),
    #
    (t_3, t_2, t_1),
    (t_3, None, t_1),
    (t_3, t_2, None),
    (t_3, None, None)]

res_ids = [uuidutils.generate_uuid() for i in range(16)]
parent_ids = [uuidutils.generate_uuid() for i in range(16)]

db_data_list = [
    {
         'id': res_ids[i],
         'resource_type': const.IPVS_REALSERVER,
         'parent_id': parent_ids[i],
         'created_at': cases_ts[i][0],
         'updated_at': cases_ts[i][1],
         'deleted_at': cases_ts[i][2],
         'extra': '',
    }
    for i in range(16)
]
with context.session.begin():
    context.session.bulk_insert_mappings(models.Revision, db_data_list)
rev_db = revisions.RevisionDbMixin()

revs = rev_db.get_revisions(context, str(t0), None)
rev_cases = [res_ids.index(rev[3]) for rev in revs]
rev_cases.sort()
assert rev_cases == valid_cases
