#!/usr/bin/python2.7

import sys

from networking_ipvs.tests.driver import get_driver
from networking_ipvs.tests.driver import test_driver


driver_name = len(sys.argv) >= 2 and sys.argv[1] or '""'
driver_cls = get_driver.driver(driver_name)
if not driver_cls:
    print 'No driver class found by name %s' % driver_name
    sys.exit(1)

single_test = len(sys.argv) >= 3 and sys.argv[2] or None
tests = test_driver.TestDriver(driver_cls)
tests.run(single_test)
