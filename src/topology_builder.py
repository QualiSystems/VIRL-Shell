#!/usr/bin/python
# -*- coding: utf-8 -*-

import ipaddress

from lxml import etree
from lxml.builder import ElementMaker

from templates import configurations as config

TOPOLOGY_WITH_NS = """<topology xmlns="http://www.cisco.com/VIRL" 
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
schemaVersion="0.95" 
xsi:schemaLocation="http://www.cisco.com/VIRL https://raw.github.com/CiscoVIRL/schema/v0.95/virl.xsd">"""


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
    def __init__(self, resources, connections, subnets, default_gateway):
        """  """

        self.resources = resources
        self.connections = connections
        self.subnets = subnets
        self.default_gateway = default_gateway

    def create_config(self, node):
        """ Create configuration based on node """

        config_class = getattr(config, node.subtype.replace(" ", "_").replace("-", "_"))
        if not config_class:
            return ""

        conf = config_class(node)

        return conf.config_builder()

    def get_ip_address(self, network, used_addresses=None):
        """  """

        if used_addresses is None:
            used_addresses = []

        net = ipaddress.ip_network(network)
        netmask = net.netmask

        for ip in net.hosts():
            if ip not in used_addresses:
                return ip, netmask

    def create_topology(self):
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
                    iface_addr, netmask = self.get_ip_address(connection.get("network"), local_used_address)
                    local_used_address.append(iface_addr)
                    ifaces.append(IFace(id=str(iface_id),
                                        address=str(iface_addr),
                                        netmask=str(netmask),
                                        description="to {}".format(src if src == node_name else dst)))
                    iface_id += 1

            node = Node(name=node_name,
                        subtype=params.get("image type", "IOSv"),
                        is_launch=params.get("autostart", "False"))

            node.user = params.get("User")
            node.password = params.get("Password")
            node.en_password = params.get("Enable Password")
            node.default_gateway = self.default_gateway
            node.address = params.get("ip address", "")
            # node.ifaces = [
            #     IFace(id="0", address="10.0.0.2", netmask="255.255.255.0", description="Description should be here")]
            node.ifaces = ifaces
            node.config = self.create_config(node=node)
            nodes.append(node)

        # Create Unmanagement Switch node for CS Subnet instance
        for node_name, network in self.subnets.items():
            ifaces = []
            iface_id = 0
            for connection in self.connections:
                src, dst = connection.get("src"), connection.get("dst")
                if src == node_name or dst == node_name:
                    iface_addr, netmask = self.get_ip_address(connection.get("network"), local_used_address)
                    local_used_address.append(iface_addr)
                    ifaces.append(IFace(id=str(iface_id),
                                        address=str(iface_addr),
                                        netmask=str(netmask),
                                        description="to {}".format(src if src == node_name else dst)))
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

            for index, node in enumerate(nodes):
                if node.name == connection.get("src"):
                    src_id = index + 1
                    for iface in node.ifaces:
                        if ipaddress.ip_address(iface.address) in ipaddress.ip_network(network):
                            src_iface_id = int(iface.id) + 1
                            break

                elif node.name == connection.get("dst"):
                    dst_id = index + 1
                    for iface in node.ifaces:
                        if ipaddress.ip_address(iface.address) in ipaddress.ip_network(network):
                            dst_iface_id = int(iface.id) + 1
                            break

                if bool(src_id and src_iface_id and dst_id and dst_iface_id):
                    break

            conns.append(Connection(src_node_id=src_id,
                                    src_iface_id=src_iface_id,
                                    dst_node_id=dst_id,
                                    dst_iface_id=dst_iface_id))

        topology_data = etree.tostring(self.topology_to_xml(nodes=nodes, connections=conns),
                                       encoding="UTF-8",
                                       pretty_print=True,
                                       xml_declaration=True).decode()

        return topology_data.replace("<topology>", TOPOLOGY_WITH_NS)

    def topology_to_xml(self, nodes, connections):
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
            ifaces = [INTERFACE(id=str(iface.id), ipv4=str(iface.address)) for iface in node.ifaces]
            entries = [ENTRY("all", key="ansible_group", type="String")]
            if node.config:
                entries.append(ENTRY(node.config, key="config", type="string"))

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
                ENTRY("flat", key="management_network", type="String"),
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
                     'Password': 'quali',
                     'User': 'quali',
                     'Enable Password': 'quali'},
            'IOSv_1': {'image type': 'IOSv',
                       'autostart': 'True',
                       'startup timeout': '300',
                       'Password': 'quali',
                       'User': 'quali',
                       'Enable Password': 'quali'}},
        'connections': [{'src': 'IOSv', 'dst': 'Subnet - 10.0.0.16-10.0.0.31', 'network': '10.0.0.16/28'},
                        {'src': 'IOSv', 'dst': 'IOSv_1', 'network': '10.0.0.0/28'}],
        'subnets': {'Subnet - 10.0.0.16-10.0.0.31': '10.0.0.16/28'},
        'default_gateway': ('192.168.105.1', '192.168.105.0/24')}

    res_details = VIRL_RESOURCES
    subnet_action_id = "qwerty"
    subnet_action_cidr = "10.0.0.0/28"

    action_id = None
    for connection in res_details.get("connections", []):
        if connection.get("network") == subnet_action_cidr:
            action_id = subnet_action_id
            break
    if not action_id and subnet_action_cidr in res_details.get("subnets", {}).values():
        action_id = subnet_action_id
    # else:
    #     raise VIRLShellError(f"Couldn't find appropriate network for action id {subnet_action_id}")

    # topo = Topology(**VIRL_RESOURCES)
    # topo = Topology(resources=VIRL_RESOURCES, connections={}, subnets={}, default_gateway="192.168.26.1")

    # data = topo.create_topology()

    # print(data)
