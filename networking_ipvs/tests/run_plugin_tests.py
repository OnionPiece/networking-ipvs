#!/usr/bin/python2.7

from networking_ipvs.tests.plugin import test_plugin


for func in dir(test_plugin):
    if func.startswith('test_'):
        getattr(test_plugin, func)()
