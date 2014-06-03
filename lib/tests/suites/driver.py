from .. import *
from . import API_KEY, API_SECRET

import functools
import sys
import time
import types

from libcloud.common.types import LibcloudError
from libcloud.dns.base import Zone
from libcloud.dns.types import ZoneDoesNotExistError, ZoneAlreadyExistsError
from libcloud.dns.providers import get_driver

from dnsmadeeasy.driver import DNSMadeEasyDNSDriver, \
    DNSMadeEasyRateLimitExceededError

Driver = get_driver('dnsmadeeasy')

def drivertest(f):
    """Marks a function as a test for the DNS driver"""
    @functools.wraps(f)
    def inner():
        try:
            return f(Driver(API_KEY, API_SECRET, True))
        except DNSMadeEasyRateLimitExceededError as e:
            printf('Rate limit exceeded (0 of %d requests remaining); '
                    'terminating prematuely', e.request_limit)
            sys.exit(2)
    return test(inner)


def domain_names():
    """Yields a list of domain names unique for this session"""
    i = 1
    while True:
        yield 'example%02d.com' % i
        i += 1

domain_names = domain_names()


@test.setup
@test.teardown
def remove_zones():
    """Removes all zones after the test suite has run and waits for them to
    actually be deleted"""
    driver = Driver(API_KEY, API_SECRET, True)

    printf('Removing all zones')

    wait_duration = 8
    while True:
        remaining = driver.list_zones()
        needs_update = False

        for zone in remaining:
            try:
                # Only touch zones with no pending action
                if zone.extra.get('pendingActionId', 0) == 0:
                    driver.delete_zone(zone)
                    printf('Scheduled dletion of zone %s', zone.domain)
                    needs_update = True

            except DNSMadeEasyRateLimitExceededError as e:
                printf('Rate limit exceeded (0 of %d requests remaining); '
                    'terminating prematuely', e.request_limit)
                return

            except LibcloudError as e:
                printf('Failed to remove zone %s: %s',
                    zone.domain, str(e.value))

        # Update the list only when needed
        if needs_update:
            remaining = driver.list_zones()

        if remaining:
            printf('Zones %s remaining, waiting %d seconds...',
                ', '.join(zone.domain for zone in remaining), wait_duration)
            time.sleep(wait_duration)
            if wait_duration < 32:
                wait_duration *= 2
        else:
            return True


@test
def DNSMadeEasyDNSDriver_registered():
    """Tests that the driver is registered"""
    assert_eq(
        Driver,
        DNSMadeEasyDNSDriver)


@drivertest
def DNSMadeEasyDNSDriver_list_zones0(d):
    """Tests that DNSMadeEasyDNSDriver.list_zones returns a sequence"""
    assert isinstance(d.list_zones(), types.ListType), \
        'DNSMadeEasyDNSDriver.list_zones did not return a list'


@drivertest
def DNSMadeEasyDNSDriver_get_zone0(d):
    """Tests that DNSMadeEasyDNSDriver.get_zone fails for invalid zone ID"""
    with assert_exception(ZoneDoesNotExistError):
        d.get_zone('__invalid__')


@drivertest
def DNSMadeEasyDNSDriver_get_zone1(d):
    """Tests that DNSMadeEasyDNSDriver.get_zone returns the same value as
    create_zone"""
    domain = next(domain_names)

    zone1 = d.create_zone(domain)
    zone2 = d.get_zone(zone1.id)

    for a in ('id', 'domain', 'type', 'ttl'):
        assert_eq(
            getattr(zone1, a),
            getattr(zone2, a))


@drivertest
def DNSMadeEasyDNSDriver_delete_zone0(d):
    """Tests that DNSMadeEasyDNSDriver.delete_zone fails for invalid zone ID"""
    domain = next(domain_names)

    zone = d.create_zone(domain)
    remove_zones()

    with assert_exception(ZoneDoesNotExistError):
        d.delete_zone(zone)


@drivertest
def DNSMadeEasyDNSDriver_create_zone0(d):
    """Tests that DNSMadeEasyDNSDriver.create_zone returns a valid zone"""
    domain = next(domain_names)

    zone = d.create_zone(domain)
    wait_duration = 2
    while wait_duration <= 32:
        time.sleep(wait_duration)
        if any(z.domain == zone.domain for z in d.list_zones()):
            return
        wait_duration *= 2

    assert False, \
        'The newly created zone was not included in the zone listing'


@drivertest
def DNSMadeEasyDNSDriver_create_zone1(d):
    """Tests that DNSMadeEasyDNSDriver.create_zone fails when creating an
    already existing domain"""
    domain = next(domain_names)

    zone = d.create_zone(domain)
    with assert_exception(ZoneAlreadyExistsError):
        d.create_zone(domain)
