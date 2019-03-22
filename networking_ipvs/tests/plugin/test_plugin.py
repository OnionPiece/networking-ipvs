#!/usr/bin/python2.7

import datetime
import hashlib

from oslo_utils import uuidutils

from networking_ipvs.common import constants as const
from networking_ipvs.common import exceptions as ipvs_exc
from networking_ipvs.common import rpc
from networking_ipvs.common import template
from networking_ipvs.common import utils as ipvs_utils
from networking_ipvs import plugin
from networking_ipvs.tests.plugin import base
from networking_ipvs.tests.plugin import assert_helper as helper


case_idx = 0
_NOTIFICATIONS = []


def wrapped_db_ops(func):
    def wrap(*args, **kwargs):
        res = func(*args, **kwargs)
        with context.session.begin():
            context.session.expire_all()
        return res
    return wrap


def task_msg(msg):
    global case_idx
    case_idx += 1
    return 'Task  #%s\t%s' % (case_idx, msg)


def fake_do_notify(*args, **kwargs):
    _NOTIFICATIONS.append((args[2], args[3]))


rpc.PluginMQNotifyMech._do_notify = fake_do_notify
vs_template = template.VirtualServerTemplate()
tenant_id = uuidutils.generate_uuid()
net_id = uuidutils.generate_uuid()
# this will be a admin context
context = base.db_init()
context.tenant_id = tenant_id
ipvs_plugin = plugin.NetworkingIPVSPlugin()
# NOTE: for sqlite, use wrapped_db_ops to make ORM relationship get updated
#       in memory
ipvs_plugin._db_create = wrapped_db_ops(ipvs_plugin._db_create)
ipvs_plugin._db_update = wrapped_db_ops(ipvs_plugin._db_update)
ipvs_plugin._db_delete = wrapped_db_ops(ipvs_plugin._db_delete)
ipvs_plugin._update_revisions = wrapped_db_ops(ipvs_plugin._update_revisions)


def get_vs_info(vs_id):
    vs_get = ipvs_plugin.get_ipvs_virtualserver(context, vs_id)
    ipvs_utils.scheduler_format(vs_get)
    return vs_get


def get_all_rs(vs_id):
    return ipvs_plugin.get_ipvs_realservers(
        context, {'ipvs_virtualserver_id': [vs_id]})


class Collector(object):
    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        for lb in ipvs_plugin.get_ipvs_loadbalancers(context):
            ipvs_plugin.delete_ipvs_loadbalancer(context, lb['id'],
                                                 body={'force': True})
        return


def collect(func):
    def wrap(*args, **kwargs):
        with Collector() as gb:
            func(gb, *args, **kwargs)
        return gb
    return wrap


def assert_notify(func):
    def wrap(*args, **kwargs):
        for i in range(len(_NOTIFICATIONS)):
            _NOTIFICATIONS.pop()
        func(*args, **kwargs)
        gb = args[0]
        task_msg = getattr(gb, 'task_msg')
        notifications = [
            (k, getattr(gb, k)) for k in dir(gb) if k.startswith('ntf')]
        if notifications:
            for task_id, ntf in notifications:
                idx, expected_meth, expected_data = ntf
                tm = task_msg + ".assert_notify." + task_id
                base.assert_notified(_NOTIFICATIONS, idx, expected_meth,
                                     expected_data, tm)
        else:
            tm = task_msg + ".assert_notify.none"
            helper.assert_true(len(_NOTIFICATIONS) == 0, tm)
    return wrap


def assert_create_result(func):
    def wrap(*args, **kwargs):
        ret = func(*args, **kwargs)
        gb = args[0]
        task_msg = getattr(gb, 'task_msg')
        creates = [
            (k, getattr(gb, k)) for k in dir(gb) if k.startswith('crt')]
        getter = {const.IPVS_LOADBALANCER: ipvs_plugin.get_ipvs_loadbalancer,
                  const.IPVS_VIRTUALSERVER: ipvs_plugin.get_ipvs_virtualserver,
                  const.IPVS_REALSERVER: ipvs_plugin.get_ipvs_realserver}
        _types = {'ipvs_loadbalancer_id': const.IPVS_VIRTUALSERVER,
                  'ipvs_virtualserver_id': const.IPVS_REALSERVER,
                  const.VIRTUALSERVERS: const.IPVS_LOADBALANCER}
        for task_id, res in creates:
            _type = [_types[_t] for _t in _types if _t in res][0]
            db_get = getter[_type](context, res['id'])
            tm = task_msg + ".assert_create_result." + task_id
            helper.assert_dict_equals(res, db_get, tm)
    return wrap


def assert_update_result(func):
    def wrap(*args, **kwargs):
        ret = func(*args, **kwargs)
        gb = args[0]
        task_msg = getattr(gb, 'task_msg')
        updates = [
            (k, getattr(gb, k)) for k in dir(gb) if k.startswith('upd')]
        getter = {const.IPVS_LOADBALANCER: ipvs_plugin.get_ipvs_loadbalancer,
                  const.IPVS_VIRTUALSERVER: ipvs_plugin.get_ipvs_virtualserver,
                  const.IPVS_REALSERVER: ipvs_plugin.get_ipvs_realserver}
        _types = {'ipvs_loadbalancer_id': const.IPVS_VIRTUALSERVER,
                  'ipvs_virtualserver_id': const.IPVS_REALSERVER,
                  const.VIRTUALSERVERS: const.IPVS_LOADBALANCER}
        for task_id, res in updates:
            _type = res.pop('type')
            db_get = getter[_type](context, res['id'])
            ob = {k: db_get[k] for k in res}
            tm = task_msg + ".assert_update_result." + task_id
            helper.assert_dict_equals(ob, res, tm)
    return wrap


def assert_delete_result(func):
    def wrap(*args, **kwargs):
        ret = func(*args, **kwargs)
        gb = args[0]
        task_msg = getattr(gb, 'task_msg')
        deletes = [
            (k, getattr(gb, k)) for k in dir(gb) if k.startswith('dlt')]
        getter = {const.IPVS_LOADBALANCER: ipvs_plugin.get_ipvs_loadbalancer,
                  const.IPVS_VIRTUALSERVER: ipvs_plugin.get_ipvs_virtualserver,
                  const.IPVS_REALSERVER: ipvs_plugin.get_ipvs_realserver}
        _types = {'ipvs_loadbalancer_id': const.IPVS_VIRTUALSERVER,
                  'ipvs_virtualserver_id': const.IPVS_REALSERVER,
                  const.VIRTUALSERVERS: const.IPVS_LOADBALANCER}
        for task_id, res in deletes:
            _type = res.pop('type')
            try:
                getter[_type](context, res['id'])
            except ipvs_exc.ResourceNotFound:
                print "%s.assert_deleted_result.%s...passed" % (
                     task_msg, task_id)
            else:
                print "%s.assert_deleted_result.%s...failed" % (
                     task_msg, task_id)
                os.sys.exit(1)
    return wrap


def assert_revisions(func):
    def wrap(*args, **kwargs):
        ret = func(*args, **kwargs)
        gb = args[0]
        task_msg = getattr(gb, 'task_msg')
        revisions = [
            (k, getattr(gb, k)) for k in dir(gb) if k.startswith('rev')]
        for (task_id, rev) in revisions:
            _id, c_at, u_at, d_at, extra = rev
            base.assert_revision(
                ipvs_plugin._get_revision, c_at, u_at, d_at, extra,
                task_msg + ".assert_revisions." + task_id, context, _id)
    return wrap


def assert_exception(func):
    def wrap(*args, **kwargs):
        func(*args, **kwargs)
        gb = args[0]
        task_msg = getattr(gb, 'task_msg')
        exceptions = [
            (k, getattr(gb, k)) for k in dir(gb) if k.startswith('expt')]
        for task_id, expt in exceptions:
            exc, exc_type = expt
            try:
                assert isinstance(exc, exc_type)
            except AssertionError:
                print task_msg + ".assert_exception." + task_id + "...failed"
                os.sys.exit(1)
    return wrap


def init_lb(up=True):
    return ipvs_plugin.create_ipvs_loadbalancer(
        context, base.lb_create_body(tenant_id, up))


# sche: scheduler, fwrd: forward_method
def init_vs(lb_id, listen_ip=None, listen_port=8080, sche=const.SOURCE_IP,
            fwrd=const.DR, up=True):
    return ipvs_plugin.create_ipvs_virtualserver(
        context, base.vs_create_body(tenant_id, lb_id, net_id, listen_ip,
                                     listen_port, sche=sche, fwrd=fwrd, up=up))


# t: weight, d: delay, t: timeout, r: max_retries
def init_rs(vs_id, server_ip='192.168.200.100', server_port=8080, w=1, d=3,
            t=3, r=3, up=True):
    return ipvs_plugin.create_ipvs_realserver(
        context, base.rs_create_body(
            tenant_id, vs_id, server_ip, server_port, up=up))


def get_created_at(_id):
    return ipvs_plugin._get_revision(context, _id).created_at


def get_updated_at(_id):
    return ipvs_plugin._get_revision(context, _id).updated_at


def get_deleted_at(_id):
    return ipvs_plugin._get_revision(context, _id).deleted_at


def get_vs_extra(vs):
    return '%s:%s-:' % (vs[const.LISTEN_IP], vs[const.LISTEN_PORT])


def get_rs_extra(vs, rs):
    return '%s:%s-%s:%s' % (vs[const.LISTEN_IP], vs[const.LISTEN_PORT],
                            rs[const.SERVER_IP], rs[const.SERVER_PORT])


def get_vs_md5(vs_info, all_rs):
    return hashlib.md5(
        vs_template.get_virtualserver_conf(vs_info, all_rs)).hexdigest()


def now():
    return datetime.datetime.utcnow()


def get_ts(_id):
    ts = ipvs_plugin._get_timestamp(context, _id)


def get_rs_notify_body(vs_info, rs):
    ret = {k: rs[k] for k in [const.SERVER_IP, const.SERVER_PORT, const.ID]}
    ret.update({k: vs_info[k] for k in [const.LISTEN_IP, const.LISTEN_PORT]})
    return ret


def update_rs_create_notify(res_dict, vs_info, rs):
    res_dict.update({k: rs[k] for k in const.REALSERVER_NOTIFY_KEYS})
    res_dict.update({k: vs_info[k] for k in const.VIRTUALSERVER_NOTIFY_KEYS})


def get_rs_update_notify(rs):
    return {k: rs[k] for k in const.REALSERVER_NOTIFY_KEYS + [
        const.ID, const.SERVER_IP, const.SERVER_PORT]}


def update_rs_update_notify(res_dict, rs):
    res_dict.update({k: rs[k] for k in const.REALSERVER_NOTIFY_KEYS})


@collect
@assert_notify
@assert_revisions
@assert_create_result
def test_lb_creation(gb):
    gb.task_msg = task_msg('test create lb')
    gb.crt_lb_db_1 = init_lb()
    gb.rev_1 = (gb.crt_lb_db_1['id'], 0, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_create_result
def test_vs_creation(gb):
    lb = init_lb()
    gb.task_msg = task_msg('test create vs')
    gb.crt_vs_db_1 = init_vs(lb['id'], '192.168.0.100', 8080)
    vs1_created_at = get_created_at(gb.crt_vs_db_1['id'])
    try:
        init_vs(lb['id'], '192.168.0.100', 8080)
    except Exception as e:
        gb.expt_e1 = (e, ipvs_exc.VirtualServerEntityExists)

    gb.crt_vs_db_2 = init_vs(lb['id'], '192.168.0.100', 8081)
    vs2_created_at = get_created_at(gb.crt_vs_db_2['id'])
    gb.rev_1 = (gb.crt_vs_db_1['id'], 0, None, None, None)
    gb.rev_2 = (gb.crt_vs_db_2['id'], 0, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_create_result
def test_rs_creation(gb):
    gb.task_msg = task_msg('test create rs')
    lb = init_lb()
    vs = init_vs(lb['id'])
    vs_info = get_vs_info(vs['id'])
    vs_created_at = get_created_at(vs['id'])

    gb.crt_rs = init_rs(vs['id'])
    md5 = get_vs_md5(vs_info, [gb.crt_rs])
    gb.rev_1 = (vs['id'], vs_created_at, None, None, md5)
    expected_meth = 'create_realserver'
    expected_data = get_rs_notify_body(vs_info, gb.crt_rs)
    update_rs_create_notify(expected_data, vs_info, gb.crt_rs)
    ts = get_created_at(gb.crt_rs['id'])
    expected_data.update({const.TIMESTAMP: ts, const.MD5: md5})
    gb.ntf_1 = (0, expected_meth, expected_data)
    gb.rev_2 = (gb.crt_rs['id'], ts, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_create_result
def test_rs_creation_exception(gb):
    gb.task_msg = task_msg('test create rs exception')
    lb = init_lb()
    vs = init_vs(lb['id'])
    vs_info = get_vs_info(vs['id'])
    vs_created_at = get_created_at(vs['id'])

    gb.crt_rs = init_rs(vs['id'])
    try:
        init_rs(vs['id'])
    except Exception as e:
        gb.expt_1 = (e, ipvs_exc.RealServerEntityExists)
    md5 = get_vs_md5(vs_info, [gb.crt_rs])
    gb.rev_1 = (vs['id'], vs_created_at, None, None, md5)
    expected_meth = 'create_realserver'
    expected_data = get_rs_notify_body(vs_info, gb.crt_rs)
    update_rs_create_notify(expected_data, vs_info, gb.crt_rs)
    ts = get_created_at(gb.crt_rs['id'])
    expected_data.update({const.TIMESTAMP: ts, const.MD5: md5})
    gb.ntf_1 = (0, expected_meth, expected_data)
    gb.rev_2 = (gb.crt_rs['id'], ts, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_create_result
def test_rs_creation_same_rs_on_two_vs(gb):
    gb.task_msg = task_msg('test create rs same rs on two vs')
    lb = init_lb()
    vs1 = init_vs(lb['id'])
    vs1_info = get_vs_info(vs1['id'])
    vs2 = init_vs(lb['id'])
    vs2_info = get_vs_info(vs2['id'])
    vs_created_at = now()

    # rs_1 and rs_2 have the same server_ip and server_port
    gb.crt_rs1 = init_rs(vs1['id'])
    gb.crt_rs2 = init_rs(vs2['id'])
    md51 = get_vs_md5(vs1_info, [gb.crt_rs1])
    md52 = get_vs_md5(vs2_info, [gb.crt_rs2])
    gb.rev_1 = (vs1['id'], vs_created_at, None, None, md51)
    gb.rev_2 = (vs2['id'], vs_created_at, None, None, md52)
    expected_meth = 'create_realserver'
    expected_data1 = get_rs_notify_body(vs1_info, gb.crt_rs1)
    update_rs_create_notify(expected_data1, vs1_info, gb.crt_rs1)
    expected_data2 = get_rs_notify_body(vs2_info, gb.crt_rs2)
    update_rs_create_notify(expected_data2, vs2_info, gb.crt_rs2)
    ts1 = get_created_at(gb.crt_rs1['id'])
    ts2 = get_created_at(gb.crt_rs2['id'])
    expected_data1.update({const.TIMESTAMP: ts1, const.MD5: md51})
    expected_data2.update({const.TIMESTAMP: ts2, const.MD5: md52})
    gb.ntf_1 = (0, expected_meth, expected_data1)
    gb.ntf_2 = (1, expected_meth, expected_data2)
    gb.rev_3 = (gb.crt_rs1['id'], ts1, None, None, None)
    gb.rev_4 = (gb.crt_rs2['id'], ts2, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_create_result
def test_rs_creation_under_down_lb(gb):
    gb.task_msg = task_msg('test create rs under down lb')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'])
    vs_info = get_vs_info(vs['id'])

    gb.crt_rs = init_rs(vs['id'])
    gb.rev_1 = (vs['id'], 0, None, None, None)
    gb.rev_2 = (gb.crt_rs['id'], 0, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_create_result
def test_rs_creation_under_down_vs(gb):
    gb.task_msg = task_msg('test create rs under down vs')
    lb = init_lb()
    vs = init_vs(lb['id'], up=False)
    vs_info = get_vs_info(vs['id'])

    gb.crt_rs = init_rs(vs['id'])
    gb.rev_1 = (vs['id'], 0, None, None, None)
    gb.rev_2 = (gb.crt_rs['id'], 0, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_lb_common_attr(gb):
    gb.task_msg = task_msg('test update lb common attr')
    lb = init_lb()
    lb_update = base.lb_update_body()
    base.update_name(lb_update, 'xxx')
    ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    gb.upd_1 = {'id': lb['id'], 'name': 'xxx', 'type': const.IPVS_LOADBALANCER}
    gb.rev_1 = (lb['id'], 0, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_lb_down(gb):
    gb.task_msg = task_msg('test update lb down')
    lb = init_lb()
    lb_update = base.lb_update_body()
    base.update_down(lb_update)
    ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_LOADBALANCER}
    gb.rev_1 = (lb['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_update_result
def test_update_lb_down_with_exception(gb):
    gb.task_msg = task_msg('test update lb down with exception')
    lb = init_lb()
    lb_update = base.lb_update_body()
    base.update_down(lb_update)
    base.update_name(lb_update, 'xxx')
    try:
        ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    except Exception as e:
        gb.expt_1 = (e, ipvs_exc.AdminStateUpCannotUpdateWithOtherAttr)
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_LOADBALANCER}
    gb.rev_1 = (lb['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_lb_up(gb):
    gb.task_msg = task_msg('test update lb up')
    lb = init_lb(up=False)
    lb_update = base.lb_update_body()
    base.update_up(lb_update)
    ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_LOADBALANCER}
    gb.rev_1 = (lb['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_update_result
def test_update_lb_up_with_exception(gb):
    gb.task_msg = task_msg('test update lb up with exception')
    lb = init_lb(up=False)
    lb_update = base.lb_update_body()
    base.update_up(lb_update)
    base.update_name(lb_update, 'xxx')
    try:
        ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    except Exception as e:
        gb.expt_1 = (e, ipvs_exc.AdminStateUpCannotUpdateWithOtherAttr)
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_LOADBALANCER}
    gb.rev_1 = (lb['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_lb_down_with_vs(gb):
    gb.task_msg = task_msg('test update lb down with vs')
    lb = init_lb()
    vs = init_vs(lb['id'])
    lb_update = base.lb_update_body()
    base.update_down(lb_update)
    ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_LOADBALANCER}
    gb.upd_2 = {'id': vs['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.rev_1 = (lb['id'], 0, 0, None, None)
    gb.rev_2 = (vs['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_lb_down_with_vs_with_rs(gb):
    gb.task_msg = task_msg('test update lb down with vs with rs')
    lb = init_lb()
    vs = init_vs(lb['id'])
    rs = init_rs(vs['id'])
    created_at = now()
    lb_update = base.lb_update_body()
    base.update_down(lb_update)
    ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    updated_at = now()
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_LOADBALANCER}
    gb.upd_2 = {'id': vs['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_3 = {'id': rs['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_REALSERVER}
    vs_info = get_vs_info(vs['id'])
    rs = ipvs_plugin.get_ipvs_realserver(context, rs['id'])
    md5 = get_vs_md5(vs_info, [rs])
    gb.rev_1 = (lb['id'], created_at, updated_at, None, None)
    gb.rev_2 = (vs_info['id'], created_at, updated_at, None, md5)
    gb.rev_3 = (rs['id'], created_at, updated_at, None, None)
    expected_meth = 'update_virtualservers'
    expected_data = {
        const.TIMESTAMP: get_updated_at(lb['id']),
        const.ADMIN_STATE_UP: False,
        const.VIRTUALSERVERS: {
            vs_info['id']: {k: vs_info[k] for k in (
                const.ID, const.LISTEN_IP, const.LISTEN_PORT)}}}
    expected_data[const.VIRTUALSERVERS][vs_info['id']][const.MD5] = md5
    gb.ntf_1 = (1, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_lb_down_with_6_vs_with_6_rs(gb):
    gb.task_msg = task_msg('test update lb down with 6 vs with 6 rs')
    lb = init_lb()
    vs1 = init_vs(lb['id'])
    vs2 = init_vs(lb['id'])
    vs3 = init_vs(lb['id'])
    vs4 = init_vs(lb['id'], up=False)
    vs5 = init_vs(lb['id'], up=False)
    vs6 = init_vs(lb['id'], up=False)
    rs1 = init_rs(vs1['id'], '192.168.200.21')
    rs2 = init_rs(vs1['id'], '192.168.200.22')
    rs3 = init_rs(vs2['id'], '192.168.200.23')
    rs4 = init_rs(vs4['id'], '192.168.200.24')
    rs5 = init_rs(vs4['id'], '192.168.200.25', up=False)
    rs6 = init_rs(vs5['id'], '192.168.200.26', up=False)
    created_at = now()
    lb_update = base.lb_update_body()
    base.update_down(lb_update)
    ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    updated_at = now()
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_LOADBALANCER}
    gb.upd_2 = {'id': vs1['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_3 = {'id': vs2['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_4 = {'id': vs3['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_5 = {'id': vs4['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_6 = {'id': vs5['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_7 = {'id': vs6['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_8 = {'id': rs1['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_REALSERVER}
    gb.upd_9 = {'id': rs2['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_REALSERVER}
    gb.upd_10 = {'id': rs3['id'], const.ADMIN_STATE_UP: False,
                 'type': const.IPVS_REALSERVER}
    gb.upd_11 = {'id': rs4['id'], const.ADMIN_STATE_UP: False,
                 'type': const.IPVS_REALSERVER}
    gb.upd_12 = {'id': rs5['id'], const.ADMIN_STATE_UP: False,
                 'type': const.IPVS_REALSERVER}
    gb.upd_13 = {'id': rs6['id'], const.ADMIN_STATE_UP: False,
                 'type': const.IPVS_REALSERVER}
    vs1_info = get_vs_info(vs1['id'])
    vs2_info = get_vs_info(vs2['id'])
    vs3_info = get_vs_info(vs3['id'])
    vs4_info = get_vs_info(vs4['id'])
    vs5_info = get_vs_info(vs5['id'])
    vs6_info = get_vs_info(vs6['id'])
    rs1 = ipvs_plugin.get_ipvs_realserver(context, rs1['id'])
    rs2 = ipvs_plugin.get_ipvs_realserver(context, rs2['id'])
    rs3 = ipvs_plugin.get_ipvs_realserver(context, rs3['id'])
    rs4 = ipvs_plugin.get_ipvs_realserver(context, rs4['id'])
    rs5 = ipvs_plugin.get_ipvs_realserver(context, rs5['id'])
    rs6 = ipvs_plugin.get_ipvs_realserver(context, rs6['id'])
    md51 = get_vs_md5(vs1_info, [rs1, rs2])
    md52 = get_vs_md5(vs2_info, [rs3])
    md53 = get_vs_md5(vs3_info, [])
    md54 = get_vs_md5(vs4_info, [rs4, rs5])
    md55 = get_vs_md5(vs5_info, [rs6])
    md56 = get_vs_md5(vs6_info, [])
    gb.rev_1 = (lb['id'], created_at, updated_at, None, None)
    gb.rev_2 = (vs1_info['id'], created_at, updated_at, None, md51)
    gb.rev_3 = (vs2_info['id'], created_at, updated_at, None, md52)
    gb.rev_4 = (vs3_info['id'], created_at, updated_at, None, md53)
    gb.rev_5 = (vs4_info['id'], created_at, updated_at, None, md54)
    gb.rev_6 = (vs5_info['id'], created_at, updated_at, None, md55)
    gb.rev_7 = (vs6_info['id'], created_at, updated_at, None, md56)
    gb.rev_8 = (rs1['id'], created_at, updated_at, None, None)
    gb.rev_9 = (rs2['id'], created_at, updated_at, None, None)
    gb.rev_10 = (rs3['id'], created_at, updated_at, None, None)
    gb.rev_11 = (rs4['id'], created_at, updated_at, None, None)
    gb.rev_12 = (rs5['id'], created_at, updated_at, None, None)
    gb.rev_13 = (rs6['id'], created_at, updated_at, None, None)
    expected_meth = 'update_virtualservers'
    expected_data = {
        const.TIMESTAMP: get_updated_at(lb['id']),
        const.ADMIN_STATE_UP: False,
        const.VIRTUALSERVERS: {
            vs['id']: {k: vs[k] for k in (const.ID, const.LISTEN_IP,
                                          const.LISTEN_PORT)}
            for vs in (vs1_info, vs2_info, vs3_info, vs4_info, vs5_info,
                       vs6_info)}}
    expected_data[const.VIRTUALSERVERS][vs1_info['id']][const.MD5] = md51
    expected_data[const.VIRTUALSERVERS][vs2_info['id']][const.MD5] = md52
    expected_data[const.VIRTUALSERVERS][vs3_info['id']][const.MD5] = md53
    expected_data[const.VIRTUALSERVERS][vs4_info['id']][const.MD5] = md54
    expected_data[const.VIRTUALSERVERS][vs5_info['id']][const.MD5] = md55
    expected_data[const.VIRTUALSERVERS][vs6_info['id']][const.MD5] = md56
    gb.ntf_1 = (3, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_lb_up_with_vs(gb):
    gb.task_msg = task_msg('test update lb up with vs')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'], up=False)
    lb_update = base.lb_update_body()
    base.update_up(lb_update)
    ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_LOADBALANCER}
    gb.upd_2 = {'id': vs['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.rev_1 = (lb['id'], 0, 0, None, None)
    gb.rev_2 = (vs['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_lb_up_with_vs_with_rs(gb):
    gb.task_msg = task_msg('test update lb up with vs with rs')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'], up=False)
    rs = init_rs(vs['id'], up=False)
    created_at = now()
    lb_update = base.lb_update_body()
    base.update_up(lb_update)
    ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    updated_at = now()
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_LOADBALANCER}
    gb.upd_2 = {'id': vs['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_3 = {'id': rs['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_REALSERVER}
    vs_info = get_vs_info(vs['id'])
    rs = ipvs_plugin.get_ipvs_realserver(context, rs['id'])
    md5 = get_vs_md5(vs_info, [rs])
    gb.rev_1 = (lb['id'], created_at, updated_at, None, None)
    gb.rev_2 = (vs['id'], created_at, updated_at, None, md5)
    gb.rev_3 = (rs['id'], created_at, updated_at, None, None)
    expected_meth = 'update_virtualservers'
    expected_data = {
        const.TIMESTAMP: get_updated_at(lb['id']),
        const.ADMIN_STATE_UP: True,
        const.VIRTUALSERVERS: {
            vs_info['id']: {k: vs_info[k] for k in [
                const.ID, const.LISTEN_IP,
                const.LISTEN_PORT] + const.VIRTUALSERVER_NOTIFY_KEYS}}}
    expected_data[const.VIRTUALSERVERS][vs_info['id']][const.MD5] = md5
    expected_data[const.VIRTUALSERVERS][vs_info['id']][const.REALSERVERS] = [
        get_rs_update_notify(rs)]
    gb.ntf_1 = (0, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_lb_up_with_6_vs_with_6_rs(gb):
    gb.task_msg = task_msg('test update lb up with 6 vs with 6 rs')
    lb = init_lb(up=False)
    vs1 = init_vs(lb['id'], up=False)
    vs2 = init_vs(lb['id'])
    vs3 = init_vs(lb['id'], up=False)
    vs4 = init_vs(lb['id'])
    vs5 = init_vs(lb['id'], up=False)
    vs6 = init_vs(lb['id'])
    rs1 = init_rs(vs1['id'], '192.168.200.20', up=False)
    rs2 = init_rs(vs1['id'], '192.168.200.21')
    rs3 = init_rs(vs2['id'], '192.168.200.22', up=False)
    rs4 = init_rs(vs2['id'], '192.168.200.23')
    rs5 = init_rs(vs3['id'], '192.168.200.24')
    rs6 = init_rs(vs4['id'], '192.168.200.25', up=False)
    created_at = now()
    lb_update = base.lb_update_body()
    base.update_up(lb_update)
    ipvs_plugin.update_ipvs_loadbalancer(context, lb['id'], lb_update)
    updated_at = now()
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_LOADBALANCER}
    gb.upd_2 = {'id': vs1['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_3 = {'id': vs2['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_4 = {'id': vs3['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_5 = {'id': vs4['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_6 = {'id': vs5['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_7 = {'id': vs6['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_8 = {'id': rs1['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_REALSERVER}
    gb.upd_9 = {'id': rs2['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_REALSERVER}
    gb.upd_10 = {'id': rs3['id'], const.ADMIN_STATE_UP: True,
                 'type': const.IPVS_REALSERVER}
    gb.upd_11 = {'id': rs4['id'], const.ADMIN_STATE_UP: True,
                 'type': const.IPVS_REALSERVER}
    gb.upd_12 = {'id': rs5['id'], const.ADMIN_STATE_UP: True,
                 'type': const.IPVS_REALSERVER}
    gb.upd_13 = {'id': rs6['id'], const.ADMIN_STATE_UP: True,
                 'type': const.IPVS_REALSERVER}
    vs1_info = get_vs_info(vs1['id'])
    vs2_info = get_vs_info(vs2['id'])
    vs3_info = get_vs_info(vs3['id'])
    vs4_info = get_vs_info(vs4['id'])
    vs5_info = get_vs_info(vs5['id'])
    vs6_info = get_vs_info(vs6['id'])
    rs1 = ipvs_plugin.get_ipvs_realserver(context, rs1['id'])
    rs2 = ipvs_plugin.get_ipvs_realserver(context, rs2['id'])
    rs3 = ipvs_plugin.get_ipvs_realserver(context, rs3['id'])
    rs4 = ipvs_plugin.get_ipvs_realserver(context, rs4['id'])
    rs5 = ipvs_plugin.get_ipvs_realserver(context, rs5['id'])
    rs6 = ipvs_plugin.get_ipvs_realserver(context, rs6['id'])
    md51 = get_vs_md5(vs1_info, [rs1, rs2])
    md52 = get_vs_md5(vs2_info, [rs3, rs4])
    md53 = get_vs_md5(vs3_info, [rs5])
    md54 = get_vs_md5(vs4_info, [rs6])
    md55 = get_vs_md5(vs5_info, [])
    md56 = get_vs_md5(vs6_info, [])
    gb.rev_1 = (lb['id'], created_at, updated_at, None, None)
    gb.rev_2 = (vs1_info['id'], created_at, updated_at, None, md51)
    gb.rev_3 = (vs2_info['id'], created_at, updated_at, None, md52)
    gb.rev_4 = (vs3_info['id'], created_at, updated_at, None, md53)
    gb.rev_5 = (vs4_info['id'], created_at, updated_at, None, md54)
    gb.rev_6 = (vs5_info['id'], created_at, updated_at, None, md55)
    gb.rev_7 = (vs6_info['id'], created_at, updated_at, None, md56)
    gb.rev_8 = (rs1['id'], created_at, updated_at, None, None)
    gb.rev_9 = (rs2['id'], created_at, updated_at, None, None)
    gb.rev_10 = (rs3['id'], created_at, updated_at, None, None)
    gb.rev_11 = (rs4['id'], created_at, updated_at, None, None)
    gb.rev_12 = (rs5['id'], created_at, updated_at, None, None)
    gb.rev_13 = (rs6['id'], created_at, updated_at, None, None)
    expected_meth = 'update_virtualservers'
    expected_data = {
        const.TIMESTAMP: get_updated_at(lb['id']),
        const.ADMIN_STATE_UP: True,
        const.VIRTUALSERVERS: {
            vs['id']: {k: vs[k] for k in [
                const.ID, const.LISTEN_IP,
                const.LISTEN_PORT] + const.VIRTUALSERVER_NOTIFY_KEYS}
            for vs in (vs1_info, vs2_info, vs3_info, vs4_info, vs5_info,
                       vs6_info)}}
    for vs, md5, all_rs in ((vs1_info, md51, [rs1, rs2]),
                            (vs2_info, md52, [rs3, rs4]),
                            (vs3_info, md53, [rs5]),
                            (vs4_info, md54, [rs6]),
                            (vs5_info, md55, []),
                            (vs6_info, md56, [])):
        expected_data[const.VIRTUALSERVERS][vs['id']][const.MD5] = md5
        expected_data[const.VIRTUALSERVERS][vs['id']][const.REALSERVERS] = [
            get_rs_update_notify(rs) for rs in all_rs]
    gb.ntf_1 = (0, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_vs_common_attr(gb):
    gb.task_msg = task_msg('test update vs common attr')
    lb = init_lb()
    vs = init_vs(lb['id'])
    vs_update = base.vs_update_body()
    base.update_name(vs_update, 'xxx')
    ipvs_plugin.update_ipvs_virtualserver(context, vs['id'], vs_update)
    gb.upd_1 = {'id': vs['id'], 'name': 'xxx',
                'type': const.IPVS_VIRTUALSERVER}
    gb.rev_1 = (vs['id'], 0, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_vs_notify_attr(gb):
    gb.task_msg = task_msg('test update vs notify attr')
    lb = init_lb()
    vs = init_vs(lb['id'])
    vs_update = base.vs_update_body()
    base.update_attr(vs_update, const.SCHEDULER, const.ROUND_ROBIN)
    ipvs_plugin.update_ipvs_virtualserver(context, vs['id'], vs_update)
    gb.upd_1 = {'id': vs['id'], const.SCHEDULER: const.ROUND_ROBIN,
                'type': const.IPVS_VIRTUALSERVER}
    gb.rev_1 = (vs['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_vs_up_under_up_lb(gb):
    gb.task_msg = task_msg('test update vs up under up lb')
    lb = init_lb()
    vs = init_vs(lb['id'], up=False)
    vs_update = base.vs_update_body()
    base.update_up(vs_update)
    ipvs_plugin.update_ipvs_virtualserver(context, vs['id'], vs_update)
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_LOADBALANCER}
    gb.upd_2 = {'id': vs['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.rev_1 = (lb['id'], 0, None, None, None)
    gb.rev_2 = (vs['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_vs_up_under_down_lb(gb):
    gb.task_msg = task_msg('test update vs up under down lb')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'], up=False)
    vs_update = base.vs_update_body()
    base.update_up(vs_update)
    ipvs_plugin.update_ipvs_virtualserver(context, vs['id'], vs_update)
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_LOADBALANCER}
    gb.upd_2 = {'id': vs['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.rev_1 = (lb['id'], 0, None, None, None)
    gb.rev_2 = (vs['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_vs_down_under_up_lb(gb):
    gb.task_msg = task_msg('test update vs down under up lb')
    lb = init_lb()
    vs = init_vs(lb['id'])
    vs_update = base.vs_update_body()
    base.update_down(vs_update)
    ipvs_plugin.update_ipvs_virtualserver(context, vs['id'], vs_update)
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_LOADBALANCER}
    gb.upd_2 = {'id': vs['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.rev_1 = (lb['id'], 0, None, None, None)
    gb.rev_2 = (vs['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_vs_down_under_up_down(gb):
    gb.task_msg = task_msg('test update vs down under down lb')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'])
    vs_update = base.vs_update_body()
    base.update_down(vs_update)
    ipvs_plugin.update_ipvs_virtualserver(context, vs['id'], vs_update)
    gb.upd_1 = {'id': lb['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_LOADBALANCER}
    gb.upd_2 = {'id': vs['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.rev_1 = (lb['id'], 0, None, None, None)
    gb.rev_2 = (vs['id'], 0, 0, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_vs_down_with_rs(gb):
    gb.task_msg = task_msg('test update vs down with rs')
    lb = init_lb()
    vs = init_vs(lb['id'])
    rs1 = init_rs(vs['id'], up=False)
    rs2 = init_rs(vs['id'], '192.168.200.200')
    created_at = now()
    vs_update = base.vs_update_body()
    base.update_down(vs_update)
    ipvs_plugin.update_ipvs_virtualserver(context, vs['id'], vs_update)
    updated_at = now()
    gb.upd_1 = {'id': vs['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_2 = {'id': rs1['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_REALSERVER}
    gb.upd_3 = {'id': rs2['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_REALSERVER}
    vs_info = get_vs_info(vs['id'])
    rs1 = ipvs_plugin.get_ipvs_realserver(context, rs1['id'])
    rs2 = ipvs_plugin.get_ipvs_realserver(context, rs2['id'])
    md5 = get_vs_md5(vs_info, [rs1, rs2])
    gb.rev_1 = (vs['id'], created_at, updated_at, None, md5)
    gb.rev_2 = (rs1['id'], created_at, updated_at, None, None)
    gb.rev_3 = (rs2['id'], created_at, updated_at, None, None)
    expected_meth = 'update_virtualserver'
    expected_data = {k: vs_info[k] for k in [
        const.LISTEN_IP, const.LISTEN_PORT, const.ADMIN_STATE_UP]}
    expected_data.update({
        const.MD5: md5, const.TIMESTAMP: get_updated_at(vs['id'])})
    gb.ntf_1 = (1, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_vs_up_with_rs(gb):
    gb.task_msg = task_msg('test update vs up with rs')
    lb = init_lb()
    vs = init_vs(lb['id'], up=False)
    rs1 = init_rs(vs['id'], up=False)
    rs2 = init_rs(vs['id'], '192.168.200.200')
    created_at = now()
    rs_update = base.rs_update_body()
    base.update_attr(rs_update, const.WEIGHT, 11)
    ipvs_plugin.update_ipvs_realserver(context, rs1['id'], rs_update)
    base.update_attr(rs_update, const.DELAY, 5)
    ipvs_plugin.update_ipvs_realserver(context, rs2['id'], rs_update)
    vs_update = base.vs_update_body()
    base.update_up(vs_update)
    ipvs_plugin.update_ipvs_virtualserver(context, vs['id'], vs_update)
    updated_at = now()
    gb.upd_1 = {'id': vs['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_VIRTUALSERVER}
    gb.upd_2 = {'id': rs1['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_REALSERVER}
    gb.upd_3 = {'id': rs2['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_REALSERVER}
    vs_info = get_vs_info(vs['id'])
    rs1 = ipvs_plugin.get_ipvs_realserver(context, rs1['id'])
    rs2 = ipvs_plugin.get_ipvs_realserver(context, rs2['id'])
    md5 = get_vs_md5(vs_info, [rs1, rs2])
    gb.rev_1 = (vs['id'], created_at, updated_at, None, md5)
    gb.rev_2 = (rs1['id'], created_at, updated_at, None, None)
    gb.rev_3 = (rs2['id'], created_at, updated_at, None, None)
    expected_meth = 'update_virtualserver'
    expected_data = {k: vs_info[k] for k in [
        const.LISTEN_IP, const.LISTEN_PORT] + const.VIRTUALSERVER_NOTIFY_KEYS}
    expected_data.update({
        const.MD5: md5, const.TIMESTAMP: get_updated_at(vs['id'])})
    gb.ntf_1 = (0, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_common_attr(gb):
    gb.task_msg = task_msg('test update rs common attr')
    lb = init_lb()
    vs = init_vs(lb['id'])
    rs = init_rs(vs['id'])
    _NOTIFICATIONS.pop()
    rs_update = base.rs_update_body()
    base.update_name(rs_update, 'xxx')
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    gb.upd_1 = {'id': rs['id'], 'name': 'xxx',
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], 0, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_common_attr_under_down_lb(gb):
    gb.task_msg = task_msg('test update rs common attr under down lb')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'])
    rs = init_rs(vs['id'])
    rs_update = base.rs_update_body()
    base.update_name(rs_update, 'xxx')
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    gb.upd_1 = {'id': rs['id'], 'name': 'xxx',
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], 0, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_common_attr_under_down_vs(gb):
    gb.task_msg = task_msg('test update rs common attr under down vs')
    lb = init_lb()
    vs = init_vs(lb['id'], up=False)
    rs = init_rs(vs['id'])
    rs_update = base.rs_update_body()
    base.update_name(rs_update, 'xxx')
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    gb.upd_1 = {'id': rs['id'], 'name': 'xxx',
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], 0, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_notify_attr(gb):
    gb.task_msg = task_msg('test update rs notify attr')
    lb = init_lb()
    vs = init_vs(lb['id'])
    vs_created_at = now()
    rs = init_rs(vs['id'])
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_attr(rs_update, const.WEIGHT, 2)
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.WEIGHT: 2,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    rs = ipvs_plugin.get_ipvs_realserver(context, rs['id'])
    vs_info = get_vs_info(vs['id'])
    expected_meth = 'update_realserver'
    expected_data = get_rs_notify_body(vs_info, rs)
    md5 = get_vs_md5(vs_info, [rs])
    gb.rev_2 = (vs['id'], vs_created_at, None, None, md5)
    rs_updated_at = get_updated_at(rs['id'])
    expected_data.update({const.TIMESTAMP: rs_updated_at, const.MD5: md5,
                          const.WEIGHT: 2})
    gb.ntf_1 = (1, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_notify_attr_under_down_lb(gb):
    gb.task_msg = task_msg('test update rs notify attr under down lb')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'])
    vs_created_at = now()
    rs = init_rs(vs['id'])
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_attr(rs_update, const.WEIGHT, 2)
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.WEIGHT: 2,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    rs = ipvs_plugin.get_ipvs_realserver(context, rs['id'])
    gb.rev_2 = (vs['id'], vs_created_at, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_notify_attr_under_down_vs(gb):
    gb.task_msg = task_msg('test update rs notify attr under down vs')
    lb = init_lb()
    vs = init_vs(lb['id'], up=False)
    vs_created_at = now()
    rs = init_rs(vs['id'])
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_attr(rs_update, const.WEIGHT, 2)
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.WEIGHT: 2,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    rs = ipvs_plugin.get_ipvs_realserver(context, rs['id'])
    gb.rev_2 = (vs['id'], vs_created_at, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_down(gb):
    gb.task_msg = task_msg('test update rs down')
    lb = init_lb()
    vs = init_vs(lb['id'])
    vs_created_at = now()
    rs = init_rs(vs['id'])
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_down(rs_update)
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    rs = ipvs_plugin.get_ipvs_realserver(context, rs['id'])
    vs_info = get_vs_info(vs['id'])
    expected_meth = 'update_realserver'
    expected_data = get_rs_notify_body(vs_info, rs)
    md5 = get_vs_md5(vs_info, [rs])
    gb.rev_2 = (vs['id'], vs_created_at, None, None, md5)
    rs_updated_at = get_updated_at(rs['id'])
    expected_data.update({const.ADMIN_STATE_UP: False, const.MD5: md5,
                          const.TIMESTAMP: rs_updated_at})
    gb.ntf_1 = (1, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_update_result
def test_update_rs_down_with_exception(gb):
    gb.task_msg = task_msg('test update rs down with exception')
    gb.task_msg = task_msg('test update rs down')
    lb = init_lb()
    vs = init_vs(lb['id'])
    vs_created_at = now()
    rs = init_rs(vs['id'])
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_name(rs_update, 'xxx')
    base.update_down(rs_update)
    try:
        ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    except Exception as e:
        gb.expt_1 = (e, ipvs_exc.AdminStateUpCannotUpdateWithOtherAttr)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    rs = ipvs_plugin.get_ipvs_realserver(context, rs['id'])
    vs_info = get_vs_info(vs['id'])
    expected_meth = 'update_realserver'
    expected_data = get_rs_notify_body(vs_info, rs)
    md5 = get_vs_md5(vs_info, [rs])
    gb.rev_2 = (vs['id'], vs_created_at, None, None, md5)
    rs_updated_at = get_updated_at(rs['id'])
    expected_data.update({const.ADMIN_STATE_UP: False, const.MD5: md5,
                          const.TIMESTAMP: rs_updated_at})
    gb.ntf_1 = (1, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_down_under_down_lb(gb):
    gb.task_msg = task_msg('test update rs down under down lb')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'])
    vs_created_at = now()
    rs = init_rs(vs['id'])
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_down(rs_update)
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    gb.rev_2 = (vs['id'], vs_created_at, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_down_under_down_vs(gb):
    gb.task_msg = task_msg('test update rs down under down vs')
    lb = init_lb()
    vs = init_vs(lb['id'], up=False)
    vs_created_at = now()
    rs = init_rs(vs['id'])
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_down(rs_update)
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.ADMIN_STATE_UP: False,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    gb.rev_2 = (vs['id'], vs_created_at, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_up(gb):
    gb.task_msg = task_msg('test update rs up')
    lb = init_lb()
    vs = init_vs(lb['id'])
    vs_created_at = now()
    rs = init_rs(vs['id'], up=False)
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_up(rs_update)
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    rs = ipvs_plugin.get_ipvs_realserver(context, rs['id'])
    vs_info = get_vs_info(vs['id'])
    expected_meth = 'update_realserver'
    expected_data = get_rs_notify_body(vs_info, rs)
    md5 = get_vs_md5(vs_info, [rs])
    gb.rev_2 = (vs['id'], vs_created_at, None, None, md5)
    rs_updated_at = get_updated_at(rs['id'])
    update_rs_update_notify(expected_data, rs)
    expected_data.update({const.MD5: md5, const.TIMESTAMP: rs_updated_at})
    gb.ntf_1 = (0, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_update_result
def test_update_rs_up_with_exception(gb):
    gb.task_msg = task_msg('test update rs up with exception')
    lb = init_lb()
    vs = init_vs(lb['id'])
    vs_created_at = now()
    rs = init_rs(vs['id'], up=False)
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_up(rs_update)
    base.update_name(rs_update, 'xxx')
    try:
        ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    except Exception as e:
        gb.expt_1 = (e, ipvs_exc.AdminStateUpCannotUpdateWithOtherAttr)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    rs = ipvs_plugin.get_ipvs_realserver(context, rs['id'])
    vs_info = get_vs_info(vs['id'])
    expected_meth = 'update_realserver'
    expected_data = get_rs_notify_body(vs_info, rs)
    md5 = get_vs_md5(vs_info, [rs])
    gb.rev_2 = (vs['id'], vs_created_at, None, None, md5)
    rs_updated_at = get_updated_at(rs['id'])
    update_rs_update_notify(expected_data, rs)
    expected_data.update({const.MD5: md5, const.TIMESTAMP: rs_updated_at})
    gb.ntf_1 = (0, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_up_under_down_lb(gb):
    gb.task_msg = task_msg('test update rs up under down lb')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'])
    vs_created_at = now()
    rs = init_rs(vs['id'], up=False)
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_up(rs_update)
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    gb.rev_2 = (vs['id'], vs_created_at, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_update_result
def test_update_rs_up_under_down_vs(gb):
    gb.task_msg = task_msg('test update rs up under down vs')
    lb = init_lb()
    vs = init_vs(lb['id'], up=False)
    vs_created_at = now()
    rs = init_rs(vs['id'], up=False)
    rs_created_at = now()

    rs_update = base.rs_update_body()
    base.update_up(rs_update)
    ipvs_plugin.update_ipvs_realserver(context, rs['id'], rs_update)
    rs_updated_at = now()
    gb.upd_1 = {'id': rs['id'], const.ADMIN_STATE_UP: True,
                'type': const.IPVS_REALSERVER}
    gb.rev_1 = (rs['id'], rs_created_at, rs_updated_at, None, None)
    gb.rev_2 = (vs['id'], vs_created_at, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_delete_result
def test_delete_lb_with_exception(gb):
    gb.task_msg = task_msg('test delete lb with exception')
    lb = init_lb()
    vs = init_vs(lb['id'])
    created_at = now()

    try:
        ipvs_plugin.delete_ipvs_loadbalancer(context, lb['id'])
    except Exception as e:
        gb.expt_1 = (e, ipvs_exc.ResourceInUse)
    gb.rev_1 = (vs['id'], created_at, None, None, None)
    gb.rev_2 = (lb['id'], created_at, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_delete_result
def test_delete_empty_lb(gb):
    gb.task_msg = task_msg('test delete empty lb')
    lb = init_lb()
    created_at = now()

    ipvs_plugin.delete_ipvs_loadbalancer(context, lb['id'])
    deleted_at = now()
    gb.rev_1 = (lb['id'], created_at, None, deleted_at, None)
    gb.dlt_1 = {'id': lb['id'], 'type': const.IPVS_LOADBALANCER}


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_delete_result
def test_force_delete_lb_with_empty_vs(gb):
    gb.task_msg = task_msg('test force delete lb with empty vs')
    lb = init_lb()
    vs = init_vs(lb['id'])
    created_at = now()

    ipvs_plugin.delete_ipvs_loadbalancer(
        context, lb['id'], body={'force': True})
    deleted_at = now()
    vs_extra = get_vs_extra(vs)
    gb.rev_1 = (vs['id'], created_at, None, deleted_at, vs_extra)
    gb.rev_2 = (lb['id'], created_at, None, deleted_at, None)
    gb.dlt_1 = {'id': vs['id'], 'type': const.IPVS_VIRTUALSERVER}
    gb.dlt_2 = {'id': lb['id'], 'type': const.IPVS_LOADBALANCER}


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_delete_result
def test_force_delete_lb_with_vs_with_rs(gb):
    gb.task_msg = task_msg('test force delete lb with vs with rs')
    lb = init_lb()
    vs1 = init_vs(lb['id'])
    vs2 = init_vs(lb['id'])
    rs = init_rs(vs1['id'])
    created_at = now()

    ipvs_plugin.delete_ipvs_loadbalancer(
        context, lb['id'], body={'force': True})
    deleted_at = now()
    vs1_extra = get_vs_extra(vs1)
    vs2_extra = get_vs_extra(vs2)
    rs_extra = get_rs_extra(vs1, rs)
    gb.rev_1 = (vs1['id'], created_at, None, deleted_at, vs1_extra)
    gb.rev_2 = (vs2['id'], created_at, None, deleted_at, vs2_extra)
    gb.rev_3 = (rs['id'], created_at, None, deleted_at, rs_extra)
    gb.rev_4 = (lb['id'], created_at, None, deleted_at, None)
    deleted_at = get_deleted_at(lb['id'])
    expected_meth = 'delete_virtualservers'
    expected_data = {
        const.VIRTUALSERVERS: {
            vs[const.ID]: {
                k: vs[k] for k in [const.ID, const.LISTEN_IP,
                                   const.LISTEN_PORT]}
            for vs in (vs1, vs2)},
        const.TIMESTAMP: deleted_at,
        const.ADMIN_STATE_UP: True}
    gb.ntf_1 = (1, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_exception
@assert_delete_result
def test_delete_vs_with_exception(gb):
    gb.task_msg = task_msg('test delete vs with exception')
    lb = init_lb()
    vs = init_vs(lb['id'])
    rs = init_rs(vs['id'])
    _NOTIFICATIONS.pop()
    created_at = now()
    vs_info = get_vs_info(vs['id'])
    md5 = get_vs_md5(vs_info, [rs])

    try:
        ipvs_plugin.delete_ipvs_virtualserver(context, vs['id'])
    except Exception as e:
        gb.expt_1 = (e, ipvs_exc.ResourceInUse)
    gb.rev_1 = (vs['id'], created_at, None, None, md5)
    gb.rev_2 = (rs['id'], created_at, None, None, None)


@collect
@assert_notify
@assert_revisions
@assert_delete_result
def test_force_delete_vs_under_down_lb(gb):
    gb.task_msg = task_msg('test force delete vs under down lb')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'])
    rs = init_rs(vs['id'])
    created_at = now()

    ipvs_plugin.delete_ipvs_virtualserver(
        context, vs['id'], body={'force': True})
    deleted_at = now()
    gb.dlt_1 = {'id': vs['id'], 'type': const.IPVS_VIRTUALSERVER}
    gb.dlt_2 = {'id': rs['id'], 'type': const.IPVS_REALSERVER}
    vs_extra = get_vs_extra(vs)
    rs_extra = get_rs_extra(vs, rs)
    gb.rev_1 = (vs['id'], created_at, None, deleted_at, vs_extra)
    gb.rev_2 = (rs['id'], created_at, None, deleted_at, rs_extra)


@collect
@assert_notify
@assert_revisions
@assert_delete_result
def test_force_delete_vs_with_rs(gb):
    gb.task_msg = task_msg('test force delete vs with rs')
    lb = init_lb()
    vs = init_vs(lb['id'])
    rs = init_rs(vs['id'])
    created_at = now()

    ipvs_plugin.delete_ipvs_virtualserver(
        context, vs['id'], body={'force': True})
    deleted_at = now()
    gb.dlt_1 = {'id': vs['id'], 'type': const.IPVS_VIRTUALSERVER}
    gb.dlt_2 = {'id': rs['id'], 'type': const.IPVS_REALSERVER}
    vs_extra = get_vs_extra(vs)
    rs_extra = get_rs_extra(vs, rs)
    gb.rev_1 = (vs['id'], created_at, None, deleted_at, vs_extra)
    gb.rev_2 = (rs['id'], created_at, None, deleted_at, rs_extra)
    deleted_at = get_deleted_at(vs['id'])
    expected_meth = 'delete_virtualserver'
    expected_data = {k: vs[k] for k in [const.LISTEN_IP, const.LISTEN_PORT]}
    expected_data[const.TIMESTAMP] = deleted_at
    gb.ntf_1 = (1, expected_meth, expected_data)


@collect
@assert_notify
@assert_revisions
@assert_delete_result
def test_delete_rs_under_down_lb(gb):
    gb.task_msg = task_msg('test delete rs under down lb')
    lb = init_lb(up=False)
    vs = init_vs(lb['id'])
    rs1 = init_rs(vs['id'])
    rs2 = init_rs(vs['id'], '192.168.200.200', up=False)
    created_at = now()

    ipvs_plugin.delete_ipvs_realserver(context, rs1['id'])
    ipvs_plugin.delete_ipvs_realserver(context, rs2['id'])
    rs_deleted_at = now()
    gb.dlt_1 = {'id': rs1['id'], 'type': const.IPVS_REALSERVER}
    gb.dlt_2 = {'id': rs2['id'], 'type': const.IPVS_REALSERVER}
    gb.rev_1 = (vs['id'], created_at, None, None, None)
    rs1_extra = get_rs_extra(vs, rs1)
    rs2_extra = get_rs_extra(vs, rs2)
    gb.rev_2 = (rs1['id'], created_at, None, rs_deleted_at, rs1_extra)
    gb.rev_3 = (rs2['id'], created_at, None, rs_deleted_at, rs2_extra)


@collect
@assert_notify
@assert_revisions
@assert_delete_result
def test_delete_rs_under_down_vs(gb):
    gb.task_msg = task_msg('test delete rs under down vs')
    lb = init_lb()
    vs = init_vs(lb['id'], up=False)
    rs1 = init_rs(vs['id'])
    rs2 = init_rs(vs['id'], '192.168.200.200', up=False)
    created_at = now()

    ipvs_plugin.delete_ipvs_realserver(context, rs1['id'])
    ipvs_plugin.delete_ipvs_realserver(context, rs2['id'])
    rs_deleted_at = now()
    gb.dlt_1 = {'id': rs1['id'], 'type': const.IPVS_REALSERVER}
    gb.dlt_2 = {'id': rs2['id'], 'type': const.IPVS_REALSERVER}
    gb.rev_1 = (vs['id'], created_at, None, None, None)
    rs1_extra = get_rs_extra(vs, rs1)
    rs2_extra = get_rs_extra(vs, rs2)
    gb.rev_2 = (rs1['id'], created_at, None, rs_deleted_at, rs1_extra)
    gb.rev_3 = (rs2['id'], created_at, None, rs_deleted_at, rs2_extra)


@collect
def test_quota_setting(gb):
    lb = init_lb()
    vs1 = init_vs(lb['id'])
    vs2 = init_vs(lb['id'])
    rs1 = init_rs(vs1['id'], '10.0.0.100')
    rs2 = init_rs(vs1['id'], '10.0.0.200')
    rs3 = init_rs(vs2['id'], '10.0.0.100')
    for res, ep in ((const.IPVS_LOADBALANCER, (10, 1)),
                    (const.IPVS_VIRTUALSERVER, (10, 2)),
                    (const.IPVS_REALSERVER, (100, 3))):
        ob = ipvs_plugin.get_ipvs_quotas(
            context, filters={const.QUOTA_TYPE: [res]})[0]
        ob = tuple(ob[k] for k in (const.QUOTA, const.QUOTA_USAGE))
        helper.assert_equals(
            ob, ep, task_msg('default quota test for %s only' % res))
    obs = ipvs_plugin.get_ipvs_quotas(context)
    assert len(obs) == 3
    obs = {ob[const.QUOTA_TYPE]: (ob[const.QUOTA], ob[const.QUOTA_USAGE])
           for ob in obs}
    eps = {const.IPVS_REALSERVER: (100, 3),
           const.IPVS_VIRTUALSERVER: (10, 2),
           const.IPVS_LOADBALANCER: (10, 1)}
    helper.assert_dict_equals(ob, ep, task_msg('default quotas test'))
    for i in (0, -1, 2):
        ipvs_plugin.create_ipvs_quota(
            context, base.quota_create_body(
                tenant_id, const.IPVS_VIRTUALSERVER, i))
        ob = ipvs_plugin.get_ipvs_quotas(
                context, filters={const.QUOTA_TYPE: [const.IPVS_VIRTUALSERVER]}
                )[0][const.QUOTA]
        helper.assert_equals(ob, i, task_msg('set quota valid value %s' % i))
    ipvs_plugin.create_ipvs_quota(
        context, base.quota_create_body(
            tenant_id, const.IPVS_VIRTUALSERVER, -2))
    ob = ipvs_plugin.get_ipvs_quotas(
            context, filters={const.QUOTA_TYPE: [const.IPVS_VIRTUALSERVER]}
            )[0][const.QUOTA]
    helper.assert_equals(ob, 10, task_msg('unset quota'))
    ipvs_plugin.create_ipvs_quota(
        context, base.quota_create_body(
            tenant_id, const.IPVS_VIRTUALSERVER, 2))
    helper.assert_raise_exception(
        ipvs_plugin.create_ipvs_virtualserver,
        ipvs_exc.QuotaExceed,
        task_msg('exception QuotaExceed'),
        context,
        base.vs_create_body(tenant_id, lb['id'], net_id,
                            vs1['listen_ip'], 8082))
    ipvs_plugin.create_ipvs_quota(
        context, base.quota_create_body(
            tenant_id, const.IPVS_VIRTUALSERVER, -2))
