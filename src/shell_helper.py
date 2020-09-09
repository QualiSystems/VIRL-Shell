#!/usr/bin/python
# -*- coding: utf-8 -*-

from cloudshell.cp.core.models import VmDetailsProperty, VmDetailsNetworkInterface, VmDetailsData


def create_vm_details(vm_name, mgmt_network, node_type, node_ifaces):
    """ Create the VM Details results used for both Deployment and Refresh VM Details """

    vm_instance_data = [
        VmDetailsProperty("Instance Type", node_type)  # IOSv, NX-OSv etc
    ]

    vm_network_data = []
    for iface in node_ifaces:
        network = iface.get("network")
        exclusion_network_name = f"{vm_name}-unconnected"
        if not network \
                or network == mgmt_network\
                or network.lower().startswith(exclusion_network_name.lower()):
            continue
        vm_nic = VmDetailsNetworkInterface()
        vm_nic.interfaceId = iface.get("port_id")
        vm_nic.networkId = network
        vm_nic.networkData.append(VmDetailsProperty("IP", iface.get("ipv4", "")))
        vm_nic.networkData.append(VmDetailsProperty("IPv6", iface.get("ipv6", "")))
        vm_nic.networkData.append(VmDetailsProperty("MAC Address", iface.get("mac", "")))
        vm_nic.isPrimary = iface.get("mgmt", False)
        vm_nic.isPredefined = iface.get("mgmt", False)

        vm_network_data.append(vm_nic)
    return VmDetailsData(vm_instance_data, vm_network_data, vm_name)
