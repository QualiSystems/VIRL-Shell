#!/usr/bin/python
# -*- coding: utf-8 -*-

import ipaddress

from lxml import etree
from lxml.builder import ElementMaker

from configurations.builder import ConfigBuilder

TOPOLOGY_WITH_NS = """<topology xmlns="http://www.cisco.com/VIRL" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" schemaVersion="0.95" xsi:schemaLocation="http://www.cisco.com/VIRL https://raw.github.com/CiscoVIRL/schema/v0.95/virl.xsd">"""
# AUTONETKIT = ["NX-OSv", "NX-OSv 9000", "CSR1000v"]
AUTONETKIT = ["NX-OSv"]


class Node:
    """
        ENTRY("all", key="ansible_group", type="string"),
        ENTRY("{} configuration".format(node_name), key="config", type="string"),
        ENTRY("", key="AutoNetkit.mgmt_ip", type="string"),
    """

    def __init__(self, name, subtype, is_launch="False"):
        self.name = name
        self.subtype = subtype
        self.is_launch = self._launch_flag_convert(is_launch)
        self.user = "quali"
        self.password = "quali"
        self.en_password = "en_quali"
        self.default_gateway = ""
        self.address = ""
        self.netmask = ""
        self.config = None
        self.type = "SIMPLE"
        self.snmp_community = "quali"
        self.ifaces = list()

    def _launch_flag_convert(self, autostart):
        """  """

        if autostart and autostart.lower() == "true":
            return "false"

        return "true"


class IFace:
    def __init__(self, id, address=None, netmask=None, description=""):
        self.id = id
        self.address = address
        self.netmask = netmask
        self.description = description


class Connection:
    def __init__(self, src_node_id, src_iface_id, dst_node_id, dst_iface_id):
        self.src_node_id = src_node_id
        self.src_iface_id = src_iface_id
        self.dst_node_id = dst_node_id
        self.dst_iface_id = dst_iface_id


class Topology:
    NO_IP_ADDRESS = "no ip address"

    def __init__(self, resources, connections, subnets, default_gateway_info):
        """  """

        self.resources = resources
        self.connections = connections
        self.subnets = subnets
        # self.default_gateway = default_gateway
        self.default_gateway, self.subnet = default_gateway_info

    # def _create_config(self, node, template_path):
    #     """ Create configuration based on node """
    #
    #     config_class = getattr(config, node.subtype.replace(" ", "_").replace("-", "_"))
    #     if not config_class:
    #         return ""
    #
    #     conf = config_class(node)
    #
    #     return conf.config_builder()

    def _create_config(self, node, template_path):
        """ Create configuration based on node """

        if template_path is None:
            template_path = ""
        builder = ConfigBuilder(node=node, templates_path=template_path)

        return builder.config()

    def _get_ip_address(self, network, used_addresses=None):
        """  """

        if used_addresses is None:
            used_addresses = []

        net = ipaddress.ip_network(network)
        netmask = net.netmask

        for ip in net.hosts():
            if ip not in used_addresses:
                return ip, netmask

    def create_topology(self, mgmt_net_name="flat", template_path=None):
        """  """

        # create nodes
        local_used_address = []

        nodes = []
        for node_name, params in self.resources.items():

            ifaces = []
            iface_id = 0
            for connection in self.connections:
                src, dst = connection.get("src"), connection.get("dst")
                if src == node_name or dst == node_name:
                    iface_addr, netmask = self._get_ip_address(connection.get("network"), local_used_address)
                    local_used_address.append(iface_addr)
                    ifaces.append(IFace(id=str(iface_id),
                                        address=str(iface_addr),
                                        netmask=str(netmask),
                                        description="to {}".format(dst if src == node_name else src)))
                    iface_id += 1
            for interface in range(0, int(params.get("additional interfaces", 0))):
                ifaces.append(IFace(id=str(iface_id),
                                    description="additional interface"))
                iface_id += 1

            node = Node(name=node_name,
                        subtype=params.get("image type", "IOSv"),
                        is_launch=params.get("autostart", "False"))

            node.user = params.get("User")
            node.password = params.get("Password")
            node.en_password = params.get("Enable Password")
            node.default_gateway = self.default_gateway
            node.address = params.get("ip address", "")

            node.netmask = str(ipaddress.ip_network(self.subnet).netmask)
            # node.ifaces = [
            #     IFace(id="0", address="10.0.0.2", netmask="255.255.255.0", description="Description should be here")]
            node.ifaces = ifaces
            node.config = self._create_config(node=node, template_path=template_path)
            nodes.append(node)

        # Create Unmanagement Switch node for CS Subnet instance
        for node_name, network in self.subnets.items():
            ifaces = []
            iface_id = 0
            for connection in self.connections:
                src, dst = connection.get("src"), connection.get("dst")
                if src == node_name or dst == node_name:
                    iface_addr, netmask = self._get_ip_address(connection.get("network"), local_used_address)
                    local_used_address.append(iface_addr)
                    ifaces.append(IFace(id=str(iface_id),
                                        address=str(iface_addr),
                                        netmask=str(netmask),
                                        description="to {}".format(dst if src == node_name else src)))
                    # ifaces.append(IFace(id=str(iface_id)))
                    iface_id += 1

            node = Node(name=node_name, subtype="Unmanaged Switch", is_launch="True")

            node.ifaces = ifaces
            nodes.append(node)

        # create connections
        conns = []
        for connection in self.connections:
            network = connection.get("network")
            src_id, dst_id = None, None
            src_iface_id, dst_iface_id = None, None

            for index, node in enumerate(nodes, start=1):
                if node.name == connection.get("src"):
                    for iface in node.ifaces:
                        if ipaddress.ip_address(iface.address) in ipaddress.ip_network(network) \
                                and connection.get("dst") in iface.description:
                            src_id = index
                            src_iface_id = int(iface.id) + 1
                            break

                elif node.name == connection.get("dst"):
                    for iface in node.ifaces:
                        if ipaddress.ip_address(iface.address) in ipaddress.ip_network(network) \
                                and connection.get("src") in iface.description:
                            dst_id = index
                            dst_iface_id = int(iface.id) + 1
                            break

                if bool(src_id and src_iface_id and dst_id and dst_iface_id):
                    break

            conns.append(Connection(src_node_id=src_id,
                                    src_iface_id=src_iface_id,
                                    dst_node_id=dst_id,
                                    dst_iface_id=dst_iface_id))

        topology_data = etree.tostring(self.topology_to_xml(nodes=nodes, connections=conns, mgmt_net=mgmt_net_name),
                                       encoding="UTF-8",
                                       pretty_print=True,
                                       xml_declaration=True).decode()

        return topology_data.replace("<topology>", TOPOLOGY_WITH_NS)

    def topology_to_xml(self, nodes, connections, mgmt_net="flat"):
        """  """

        builder = ElementMaker()

        TOPOLOGY = builder.topology
        EXTENSIONS = builder.extensions
        ENTRY = builder.entry
        NODE = builder.node
        INTERFACE = builder.interface
        ANNOTATIONS = builder.annotations
        CONNECTION = builder.connection

        xml_nodes = []
        for node in nodes:
            # ifaces = [INTERFACE(id=str(iface.id), ipv4=str(iface.address)) for iface in node.ifaces]
            ifaces = []
            for iface in node.ifaces:
                if iface.address:
                    ifaces.append(INTERFACE(id=str(iface.id), ipv4=str(iface.address)))
                else:
                    ifaces.append(INTERFACE(id=str(iface.id)))

            entries = [ENTRY("all", key="ansible_group", type="String"),
                       ENTRY("false", key="Auto-generate config", type="Boolean")]
            if node.config:
                entries.append(ENTRY(node.config, key="config", type="string"))

            if node.subtype in AUTONETKIT:
                entries.append(ENTRY("", key="AutoNetkit.mgmt_ip", type="string"))

            node_params = {"name": node.name, "type": node.type,
                           "subtype": node.subtype, "ipv4": str(node.address),
                           "excludeFromLaunch": node.is_launch, "location": "200,200"}

            node_params = {k: v for k, v in node_params.items() if v}

            xml_nodes.append(
                NODE(EXTENSIONS(*entries), *ifaces, **node_params))

        xml_connections = [CONNECTION(
            src="/virl:topology/virl:node[{src}]/virl:interface[{src_iface_id}]".format(src=conn.src_node_id,
                                                                                        src_iface_id=conn.src_iface_id),
            dst="/virl:topology/virl:node[{dst}]/virl:interface[{dst_iface_id}]".format(dst=conn.dst_node_id,
                                                                                        dst_iface_id=conn.dst_iface_id))
            for conn in connections]

        topology = TOPOLOGY(
            EXTENSIONS(
                ENTRY(mgmt_net, key="management_network", type="String"),
                ENTRY("false", key="management_lxc", type="Boolean"),
                ENTRY("true", key="AutoNetkit.enable_cdp", type="Boolean"),
            ),
            *xml_nodes,
            ANNOTATIONS(),
            *xml_connections
        )

        return topology


if __name__ == "__main__":
    # VIRL_RESOURCES = {
    #     "IOSv": {"Image Type": "IOSv", "AutoStart": "False", "User": "quali_user", "Password": "quali_pass",
    #              "Enable Password": "quali_enable_password"},
    # }
    VIRL_RESOURCES = {
        'resources': {
            'IOSv': {'image type': 'IOSv',
                     'autostart': 'True',
                     'startup timeout': '300',
                     "additional interfaces": 4,
                     'Password': 'quali',
                     'User': 'quali',
                     'Enable Password': 'quali'},
            # 'IOSv_1': {'image type': 'IOSv',
            #            'autostart': 'True',
            #            'startup timeout': '300',
            #            'Password': 'quali',
            #            'User': 'quali',
            #            'Enable Password': 'quali'}
                     },
        'connections': [],
        # 'connections': [{'src': 'IOSv', 'dst': 'Subnet - 10.0.0.16-10.0.0.31', 'network': '10.0.0.16/28'},
        #                 {'src': 'IOSv', 'dst': 'IOSv_1', 'network': '10.0.0.0/28'}],
        'subnets': {},
        'default_gateway_info': ('192.168.105.1', '0.0.0.0/24')
        }
    res_details = VIRL_RESOURCES
    # subnet_action_id = "qwerty"
    # subnet_action_cidr = "10.0.0.0/28"
    # action_id = None
    # for connection in res_details.get("connections", []):
    #     if connection.get("network") == subnet_action_cidr:
    #         action_id = subnet_action_id
    #         break
    # if not action_id and subnet_action_cidr in res_details.get("subnets", {}).values():
    #     action_id = subnet_action_id
    # else:
    #     raise VIRLShellError(f"Couldn't find appropriate network for action id {subnet_action_id}")
    topo = Topology(**VIRL_RESOURCES)
    # topo = Topology(resources=VIRL_RESOURCES, connections={}, subnets={}, default_gateway="192.168.26.1")
    data = topo.create_topology()
    # print(data)