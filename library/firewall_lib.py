#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2016,2017,2020,2021 Red Hat, Inc.
# Reusing some firewalld code
# Authors:
# Thomas Woerner <twoerner@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}

DOCUMENTATION = """
---
module: firewall_lib
short_description: Module for firewall role
requirements:
  - python3-firewall or python-firewall
description:
  Manage firewall with firewalld on Fedora and RHEL-7+.
author: "Thomas Woerner (@t-woerner)"
options:
  service:
    description:
      List of service name strings.
      The service names needs to be defined in firewalld configuration.
    required: false
    type: list
    elements: str
  port:
    description:
      List of ports or port range strings.
      The format of a port needs to be port=<port>[-<port>]/<protocol>.
    required: false
    type: list
    elements: str
  source_port:
    description:
      List of source port or port range strings.
      The format of a source port needs to be port=<port>[-<port>]/<protocol>.
    required: false
    type: list
    elements: str
  forward_port:
    description:
      List of forward port strings.
      The format of a forward port needs to be
      <port>[-<port>]/<protocol>;[<to-port>];[<to-addr>].
    required: false
    type: list
    elements: str
  masquerade:
    description:
      The masquerade bool setting.
    type: bool
  rich_rule:
    description:
      List of rich rule strings.
      For the format see L(Syntax for firewalld rich language rules,
      https://firewalld.org/documentation/man-pages/firewalld.richlanguage.html).
    required: false
    type: list
    elements: str
  source:
    description:
      List of source address or address range strings.
      A source address or address range is either an IP address or a network
      IP address with a mask for IPv4 or IPv6. For IPv4, the mask can be a
      network mask or a plain number. For IPv6 the mask is a plain number.
    required: false
    type: list
    elements: str
  interface:
    description:
      List of interface name strings.
    required: false
    type: list
    elements: str
  icmp_block:
    description:
      List of ICMP type strings to block.
      The ICMP type names needs to be defined in firewalld configuration.
    required: false
    type: list
    elements: str
  icmp_block_inversion:
    description:
      ICMP block inversion bool setting.
      It enables or disables inversion of ICMP blocks for a zone in firewalld.
    required: false
    type: bool
  timeout:
    description:
      The amount of time in seconds a setting is in effect.
      The timeout is usable for services, ports, source ports, forward ports,
      masquerade, rich rules or icmp blocks for runtime only.
    required: false
    type: int
    default: 0
  target:
    description:
      The firewalld Zone target.
      If the state is set to C(absent), this will reset the target to default.
    required: false
    choices: ["default", "ACCEPT", "DROP", "%%REJECT%%"]
    type: str
  zone:
    description:
      The zone name string.
      If the zone name is not given, then the default zone will be used.
    required: false
    type: str
  permanent:
    description:
      The permanent bool flag.
      Ensures settings permanently across system reboots and firewalld
      service restarts.
      If the permanent flag is not enabled, runtime is assumed.
    required: false
    type: bool
  runtime:
    description:
      The runtime bool flag.
      Ensures settings in the runtime environment that is not persistent
      across system reboots and firewalld service restarts.
    aliases: ["immediate"]
    required: false
    type: bool
    default: no
  offline:
    description:
      The offline bool flag.
      This flag enables to ensure settings also firewalld is not running.
      firewalld >= 0.3.9 is required for this.
    required: false
    type: bool
    default: no
  state:
    description:
      Ensure presence or absence of entries.
    required: true
    type: str
    choices: ["enabled", "disabled"]
"""

from ansible.module_utils.basic import AnsibleModule
from distutils.version import LooseVersion

try:
    import firewall.config

    FW_VERSION = firewall.config.VERSION

    from firewall.client import FirewallClient, Rich_Rule, FirewallClientZoneSettings

    HAS_FIREWALLD = True
except ImportError:
    HAS_FIREWALLD = False


def parse_port(module, item):
    _port, _protocol = item.split("/")
    if _protocol is None:
        module.fail_json(msg="improper port format (missing protocol?)")
    return (_port, _protocol)


def parse_forward_port(module, item):
    type_string = "forward_port"

    args = item.split(";")
    if len(args) == 3:
        __port, _to_port, _to_addr = args
    else:
        module.fail_json(msg="improper %s format: %s" % (type_string, item))

    _port, _protocol = __port.split("/")
    if _protocol is None:
        module.fail_json(msg="improper %s format (missing protocol?)" % type_string)
    if _to_port == "":
        _to_port = None
    if _to_addr == "":
        _to_addr = None

    return (_port, _protocol, _to_port, _to_addr)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            service=dict(required=False, type="list", default=[]),
            port=dict(required=False, type="list", default=[]),
            source_port=dict(required=False, type="list", default=[]),
            forward_port=dict(required=False, type="list", default=[]),
            masquerade=dict(required=False, type="bool", default=None),
            rich_rule=dict(required=False, type="list", default=[]),
            source=dict(required=False, type="list", default=[]),
            interface=dict(required=False, type="list", default=[]),
            icmp_block=dict(required=False, type="list", default=[]),
            icmp_block_inversion=dict(required=False, type="bool", default=None),
            timeout=dict(required=False, type="int", default=0),
            target=dict(
                required=False,
                type="str",
                choices=["default", "ACCEPT", "DROP", "%%REJECT%%"],
                default=None,
            ),
            zone=dict(required=False, type="str", default=None),
            permanent=dict(required=False, type="bool", default=None),
            runtime=dict(
                required=False, type="bool", aliases=["immediate"], default=None
            ),
            offline=dict(required=False, type="bool", default=None),
            state=dict(choices=["enabled", "disabled"], required=True),
        ),
        supports_check_mode=True,
    )

    if not HAS_FIREWALLD:
        module.fail_json(msg="No firewall backend could be imported.")

    service = module.params["service"]
    port = []
    for port_proto in module.params["port"]:
        port.append(parse_port(module, port_proto))
    source_port = []
    for port_proto in module.params["source_port"]:
        source_port.append(parse_port(module, port_proto))
    forward_port = []
    for item in module.params["forward_port"]:
        forward_port.append(parse_forward_port(module, item))
    masquerade = module.params["masquerade"]
    rich_rule = []
    for item in module.params["rich_rule"]:
        try:
            rule = str(Rich_Rule(rule_str=item))
            rich_rule.append(rule)
        except Exception as e:
            module.fail_json(msg="Rich Rule '%s' is not valid: %s" % (item, str(e)))
    source = module.params["source"]
    interface = module.params["interface"]
    icmp_block = module.params["icmp_block"]
    icmp_block_inversion = module.params["icmp_block_inversion"]
    timeout = module.params["timeout"]
    target = module.params["target"]
    zone = module.params["zone"]
    permanent = module.params["permanent"]
    runtime = module.params["runtime"]
    offline = module.params["offline"]
    state = module.params["state"]

    if permanent is None:
        runtime = True
    elif not permanent:
        if (runtime is not None and not runtime) and (
            offline is not None and not offline
        ):
            module.fail_json(
                msg="One of permanent, runtime or offline needs to be enabled"
            )

    if (
        masquerade is None
        and icmp_block_inversion is None
        and target is None
        and zone is None
        and len(service)
        + len(port)
        + len(source_port)
        + len(forward_port)
        + len(rich_rule)
        + len(source)
        + len(interface)
        + len(icmp_block)
        == 0
    ):
        module.fail_json(
            msg="One of service, port, source_port, forward_port, "
            "masquerade, rich_rule, source, interface, icmp_block, "
            "icmp_block_inversion, target or zone needs to be set"
        )

    # Parameter checks
    if state == "disabled":
        if timeout > 0:
            module.fail_json(msg="timeout can not be used with state: disabled")
        if masquerade:
            module.fail_json(msg="masquerade can not be used with state: disabled")

        if icmp_block_inversion:
            module.fail_json(
                msg="icmp_block_inversion can not be used with state: disabled"
            )

        # if target is not None:
        #     module.fail_json(
        #         msg="target can not be used with state: disabled"
        #     )

    if timeout > 0:
        _timeout_ok = (
            masquerade
            or len(service)
            + len(port)
            + len(source_port)
            + len(forward_port)
            + len(rich_rule)
            + len(icmp_block)
            > 0
        )

        if icmp_block_inversion is not None and not _timeout_ok:
            module.fail_json(
                msg="timeout can not be used with icmp_block_inverson only"
            )

        if len(source) > 0 and not _timeout_ok:
            module.fail_json(msg="timeout can not be used with source only")

        if len(interface) > 0 and not _timeout_ok:
            module.fail_json(msg="timeout can not be used with interface only")

        if target is not None and not _timeout_ok:
            module.fail_json(msg="timeout can not be used with target only")

    if not HAS_FIREWALLD:
        module.fail_json(msg="No firewalld")

    fw = FirewallClient()

    fw_offline = False
    if not fw.connected:
        if not offline:
            module.fail_json(
                msg="Firewalld is not running and offline operation is " "declined."
            )

        # Firewalld is not currently running, permanent-only operations
        fw_offline = True
        runtime = False
        permanent = True

        # Pre-run version checking
        if LooseVersion(FW_VERSION) < LooseVersion("0.3.9"):
            module.fail_json(
                msg="Unsupported firewalld version %s, offline operation "
                "requires >= 0.3.9" % FW_VERSION
            )

        try:
            from firewall.core.fw_test import Firewall_test

            fw = Firewall_test()

        except ImportError:
            # In firewalld version 0.7.0 this behavior changed
            from firewall.core.fw import Firewall

            fw = Firewall(offline=True)

        fw.start()
    else:
        # Pre-run version checking
        if LooseVersion(FW_VERSION) < LooseVersion("0.2.11"):
            module.fail_json(
                msg="Unsupported firewalld version %s, requires >= 0.2.11" % FW_VERSION
            )

        # Set exception handler
        def exception_handler(exception_message):
            module.fail_json(msg=exception_message)

        fw.setExceptionHandler(exception_handler)

    # Get default zone, the permanent zone and settings
    if fw_offline:
        default_zone = fw.get_default_zone()

        if zone is not None:
            if zone not in fw.zone.get_zones():
                module.fail_json(msg="Permanent zone '%s' does not exist." % zone)
        else:
            zone = default_zone

        fw_zone = fw.config.get_zone(zone)
        fw_settings = FirewallClientZoneSettings(
            list(fw.config.get_zone_config(fw_zone))
        )
    else:
        default_zone = fw.getDefaultZone()

        if zone is not None:
            if runtime and zone not in fw.getZones():
                module.fail_json(msg="Runtime zone '%s' does not exist." % zone)
            if permanent and zone not in fw.config().getZoneNames():
                module.fail_json(msg="Permanent zone '%s' does not exist." % zone)
        else:
            zone = default_zone

        fw_zone = fw.config().getZoneByName(zone)
        fw_settings = fw_zone.getSettings()

    # Firewall modification starts here

    changed = False

    # service
    for item in service:
        if state == "enabled":
            if runtime and not fw.queryService(zone, item):
                if not module.check_mode:
                    fw.addService(zone, item, timeout)
                changed = True
            if permanent and not fw_settings.queryService(item):
                if not module.check_mode:
                    fw_settings.addService(item)
                changed = True
        elif state == "disabled":
            if runtime and fw.queryService(zone, item):
                if not module.check_mode:
                    fw.removeService(zone, item)
            if permanent and fw_settings.queryService(item):
                if not module.check_mode:
                    fw_settings.removeService(item)
                changed = True

    # port
    for _port, _protocol in port:
        if state == "enabled":
            if runtime and not fw.queryPort(zone, _port, _protocol):
                if not module.check_mode:
                    fw.addPort(zone, _port, _protocol, timeout)
                changed = True
            if permanent and not fw_settings.queryPort(_port, _protocol):
                if not module.check_mode:
                    fw_settings.addPort(_port, _protocol)
                changed = True
        elif state == "disabled":
            if runtime and fw.queryPort(zone, _port, _protocol):
                if not module.check_mode:
                    fw.removePort(zone, _port, _protocol)
                changed = True
            if permanent and fw_settings.queryPort(_port, _protocol):
                if not module.check_mode:
                    fw_settings.removePort(_port, _protocol)
                changed = True

    # source_port
    for _port, _protocol in source_port:
        if state == "enabled":
            if runtime and not fw.querySourcePort(zone, _port, _protocol):
                if not module.check_mode:
                    fw.addSourcePort(zone, _port, _protocol, timeout)
                changed = True
            if permanent and not fw_settings.querySourcePort(_port, _protocol):
                if not module.check_mode:
                    fw_settings.addSourcePort(_port, _protocol)
                changed = True
        elif state == "disabled":
            if runtime and fw.querySourcePort(zone, _port, _protocol):
                if not module.check_mode:
                    fw.removeSourcePort(zone, _port, _protocol)
                changed = True
            if permanent and fw_settings.querySourcePort(_port, _protocol):
                if not module.check_mode:
                    fw_settings.removeSourcePort(_port, _protocol)
                changed = True

    # forward_port
    if len(forward_port) > 0:
        for _port, _protocol, _to_port, _to_addr in forward_port:
            if state == "enabled":
                if runtime and not fw.queryForwardPort(
                    zone, _port, _protocol, _to_port, _to_addr
                ):
                    if not module.check_mode:
                        fw.addForwardPort(
                            zone, _port, _protocol, _to_port, _to_addr, timeout
                        )
                    changed = True
                if permanent and not fw_settings.queryForwardPort(
                    _port, _protocol, _to_port, _to_addr
                ):
                    if not module.check_mode:
                        fw_settings.addForwardPort(_port, _protocol, _to_port, _to_addr)
                    changed = True
            elif state == "disabled":
                if runtime and fw.queryForwardPort(
                    zone, _port, _protocol, _to_port, _to_addr
                ):
                    if not module.check_mode:
                        fw.removeForwardPort(zone, _port, _protocol, _to_port, _to_addr)
                    changed = True
                if permanent and fw_settings.queryForwardPort(
                    _port, _protocol, _to_port, _to_addr
                ):
                    if not module.check_mode:
                        fw_settings.removeForwardPort(
                            _port, _protocol, _to_port, _to_addr
                        )
                    changed = True

    # masquerade
    if masquerade is not None:
        if masquerade:
            if runtime and not fw.queryMasquerade(zone):
                if not module.check_mode:
                    fw.addMasquerade(zone, timeout)
                changed = True
            if permanent and not fw_settings.queryMasquerade():
                if not module.check_mode:
                    fw_settings.addMasquerade()
                changed = True
        else:
            if runtime and fw.queryMasquerade(zone):
                if not module.check_mode:
                    fw.removeMasquerade(zone)
                changed = True
            if permanent and fw_settings.queryMasquerade():
                if not module.check_mode:
                    fw_settings.removeMasquerade()
                changed = True

    # rich_rule
    for item in rich_rule:
        if state == "enabled":
            if runtime and not fw.queryRichRule(zone, item):
                if not module.check_mode:
                    fw.addRichRule(zone, item, timeout)
                changed = True
            if permanent and not fw_settings.queryRichRule(item):
                if not module.check_mode:
                    fw_settings.addRichRule(item)
                changed = True
        elif state == "disabled":
            if runtime and fw.queryRichRule(zone, item):
                if not module.check_mode:
                    fw.removeRichRule(zone, item)
                changed = True
            if permanent and fw_settings.queryRichRule(item):
                if not module.check_mode:
                    fw_settings.removeRichRule(item)
                changed = True

    # source
    for item in source:
        if state == "enabled":
            if not fw.querySource(zone, item):
                if not module.check_mode:
                    fw.addSource(zone, item)
                changed = True
            if permanent and not fw_settings.querySource(item):
                if not module.check_mode:
                    fw_settings.addSource(item)
                changed = True
        elif state == "disabled":
            if fw.querySource(zone, item):
                if not module.check_mode:
                    fw.removeSource(zone, item)
                changed = True
            if permanent and fw_settings.querySource(item):
                if not module.check_mode:
                    fw_settings.removeSource(item)
                changed = True

    # interface
    for item in interface:
        if state == "enabled":
            if runtime and not fw.queryInterface(zone, item):
                if not module.check_mode:
                    fw.addInterface(zone, item)
                changed = True
            if permanent and not fw_settings.queryInterface(item):
                if not module.check_mode:
                    fw_settings.addInterface(item)
                changed = True
        elif state == "disabled":
            if runtime and fw.queryInterface(zone, item):
                if not module.check_mode:
                    fw.removeInterface(zone, item)
                changed = True
            if permanent and fw_settings.queryInterface(item):
                if not module.check_mode:
                    fw_settings.removeInterface(item)
                changed = True

    # icmp_block
    for item in icmp_block:
        if state == "enabled":
            if runtime and not fw.queryIcmpBlock(zone, item):
                if not module.check_mode:
                    fw.addIcmpBlock(zone, item, timeout)
                changed = True
            if permanent and not fw_settings.queryIcmpBlock(item):
                if not module.check_mode:
                    fw_settings.addIcmpBlock(item)
                changed = True
        elif state == "disabled":
            if runtime and fw.queryIcmpBlock(zone, item):
                if not module.check_mode:
                    fw.removeIcmpBlock(zone, item)
                changed = True
            if permanent and fw_settings.queryIcmpBlock(item):
                if not module.check_mode:
                    fw_settings.removeIcmpBlock(item)
                changed = True

    # icmp_block_inversion
    if icmp_block_inversion is not None:
        if icmp_block_inversion:
            if runtime and not fw.queryIcmpBlockInversion(zone):
                if not module.check_mode:
                    fw.addIcmpBlockInversion(zone)
                changed = True
            if permanent and not fw_settings.queryIcmpBlockInversion():
                if not module.check_mode:
                    fw_settings.addIcmpBlockInversion()
                changed = True
        else:
            if runtime and fw.queryIcmpBlockInversion(zone):
                if not module.check_mode:
                    fw.removeIcmpBlockInversion(zone)
                changed = True
            if permanent and fw_settings.queryIcmpBlockInversion():
                if not module.check_mode:
                    fw_settings.removeIcmpBlockInversion()
                changed = True

    # target
    if target is not None:
        if state == "enabled":
            if permanent and fw_settings.getTarget() != target:
                if not module.check_mode:
                    fw_settings.setTarget(target)
                changed = True
        elif state == "disabled":
            if permanent and fw_settings.getTarget() != target:
                if not module.check_mode:
                    fw_settings.setTarget(target)
                changed = True

    # apply permanent changes
    if permanent:
        if fw_offline:
            fw.config.set_zone_config(fw_zone, fw_settings.settings)
        else:
            fw_zone.update(fw_settings)

    module.exit_json(changed=changed)


#################################################

if __name__ == "__main__":
    main()
