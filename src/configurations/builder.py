#!/usr/bin/python
# -*- coding: utf-8 -*-

import os

DEVICE_INFO = {"DEFAULT": {"delimiter": "!", "port_id": 1},
               # "IOSv": {"delimiter": "!", "port_id": 1},
               # "IOSvL2": {"delimiter": "!", "port_id": 1},
               # "NX-OSv": {"delimiter": "!", "port_id": 1},
               # "NX-OSv 9000": {"delimiter": "!", "port_id": 1},
               "IOS XRv": {"delimiter": "!", "port_id": 0},
               # "IOS XRv 9000": {"delimiter": "!", "port_id": 1},
               "CSR1000v": {"delimiter": "!", "port_id": 2},
               # "ASAv": {"delimiter": "!", "port_id": 1}
               }


class ConfigBuilder:
    def __init__(self, node, templates_path):
        self.node = node

        device_template_path = os.path.join(templates_path, self.node.subtype, "device.tmpl")
        port_template_path = os.path.join(templates_path, self.node.subtype, "port.tmpl")

        build_in_templates = os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates")

        if os.path.exists(device_template_path):
            self.device_template_path = device_template_path
        else:
            self.device_template_path = os.path.join(build_in_templates, self.node.subtype, "device.tmpl")

        if os.path.exists(port_template_path):
            self.port_template_path = port_template_path
        else:
            self.port_template_path = os.path.join(build_in_templates, self.node.subtype, "port.tmpl")

    def _read_config(self, template_path):
        """  """

        with open(template_path, "r") as f:
            template = f.read()

        return template

    def ports(self, ifaces, port_id_start=1, delimiter="!"):
        """ Build configuration for all ports apart from Management """
        ports = f"\n{delimiter}\n".join(
            [self._read_config(self.port_template_path).format(id=int(iface.id) + port_id_start,
                                                               address=iface.address,
                                                               netmask=iface.netmask,
                                                               description=iface.description) for
             iface in ifaces])
        return f"\n{ports}\n"

    def config(self):
        """ Build full device configuration """

        delimiter = DEVICE_INFO.get(self.node.subtype, {}).get("delimiter", DEVICE_INFO["DEFAULT"]["delimiter"])
        port_id_start = DEVICE_INFO.get(self.node.subtype, {}).get("port_id", DEVICE_INFO["DEFAULT"]["port_id"])

        config = self._read_config(self.device_template_path).format(node_name=self.node.name,
                                                                     user=self.node.user,
                                                                     password=self.node.password,
                                                                     enable_password=self.node.en_password,
                                                                     default_gateway=self.node.default_gateway,
                                                                     address=self.node.address,
                                                                     netmask=self.node.netmask,
                                                                     snmp_community=self.node.snmp_community,
                                                                     interfaces=self.ports(ifaces=self.node.ifaces,
                                                                                           port_id_start=port_id_start,
                                                                                           delimiter=delimiter))
        return config
