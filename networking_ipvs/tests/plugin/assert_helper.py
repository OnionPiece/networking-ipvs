#!/usr/bin/python2.7

import os


def assert_true(_assert, case_msg):
    try:
        assert _assert is True
    except AssertionError:
        print case_msg + "...failed"
        os.sys.exit(1)
    else:
        print case_msg + "...passed"


def assert_false(_assert, case_msg):
    try:
        assert _assert is False
    except AssertionError:
        print case_msg + "...failed"
        os.sys.exit(1)
    else:
        print case_msg + "...passed"


def assert_equals(observed, expected, case_msg):
    try:
        assert observed == expected
    except AssertionError:
        print case_msg + "...failed"
        print observed, "!=", expected
        os.sys.exit(1)
    else:
        print case_msg + "...passed"


def assert_all_true(expected, case_msg):
    for ep in expected:
        try:
            assert ep is True
        except AssertionError:
            print case_msg + "...failed"
            print "#%s" % expected.index(ep), ep, "is not True"
            os.sys.exit(1)
    print case_msg + "...passed"


def assert_all_false(expected, case_msg):
    for ep in expected:
        try:
            assert ep is False
        except AssertionError:
            print case_msg + "...failed"
            print "#%s" % expected.index(ep), ep, "is not False"
            os.sys.exit(1)
    print case_msg + "...passed"


def assert_dict_equals(observed, expected, case_msg=None, depth=0):
    try:
        assert observed == expected
    except AssertionError:
        if case_msg:
            print case_msg + "...failed"
        ob_keys = observed.keys()
        ep_keys = expected.keys()
        print '%sMissed keys: %s' % (
            '\t' * depth, (set(ep_keys) - set(ob_keys)))
        print '%sUnexpected keys: %s' % (
            '\t' * depth, (set(ob_keys) - set(ep_keys)))
        print '%sDiffrent keys:' % ('\t' * depth)
        for k in set(ob_keys).intersection(ep_keys):
            if observed[k] != expected[k]:
                print '%s%s: [O]%s <=> [E]%s' % (
                    '\t' * depth, k, observed[k], expected[k])
                if isinstance(observed[k], dict) and isinstance(
                        expected[k], dict):
                    assert_dict_equals(observed[k], expected[k], None,
                                       depth + 1)
                else:
                    print (
                        'Cannot do deeper compare, since [O]object is %s '
                        'while [E]object is %s' % (
                            type(observed[k]), type(expected[k])))
        if depth == 0:
            os.sys.exit(1)
    else:
        if case_msg:
            print case_msg + "...passed"


def assert_raise_exception(func, exc, case_msg, *args, **kwargs):
    failed_msg = case_msg + "...failed"
    try:
        func(*args, **kwargs)
    except Exception as e:
        try:
            assert isinstance(e, exc)
        except AssertionError:
            print failed_msg
            print "%s raised, not %s" % (type(e), exc)
            os.sys.exit(1)
        else:
            print case_msg + "...passed"
    else:
        print failed_msg
        print "No exception raised"
        os.sys.exit(1)
