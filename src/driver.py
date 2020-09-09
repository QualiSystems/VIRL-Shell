#!/usr/bin/python
# -*- coding: utf-8 -*-

import ipaddress
import json
import jsonpickle
import os
import time

from requests import HTTPError

from cloudshell.shell.core.driver_context import AutoLoadDetails, ResourceRemoteCommandContext
from cloudshell.cp.core import DriverRequestParser
from cloudshell.cp.core.models import DeployApp, DeployAppResult, DriverResponse, Attribute, ConnectSubnet, \
    PrepareSubnetActionResult, ConnectToSubnetActionResult
from cloudshell.cp.core.models import PrepareCloudInfraResult, CreateKeysActionResult, ActionResultBase

from cloudshell.shell.core.resource_driver_interface import ResourceDriverInterface
from cloudshell.shell.core.session.logging_session import LoggingSessionContext

from data_model import VIRLShellDriverResource as ShellResource
from instance_details import InstanceDetails
from shell_helper import create_vm_details
from virl_exceptions import VIRLShellError

from api_utils import get_reservation_details, MIN_STARTUP_TIMEOUT
from topology_builder import Topology
from virl_api import VIRL_API, IFACE_REBOOT_TIMEOUT


class VIRLShellDriver(ResourceDriverInterface):
    # NEED_IP_ADDRESS = ["NX-OSv"]

    def __init__(self):
        """ Constructor must be without arguments, it is created with reflection at run time """
        self.request_parser = DriverRequestParser()
        self.deployments = dict()
        # Keys should be partial names of deployment paths
        self.deployments["VIRL VM"] = self.vm_from_image

    def cleanup(self):
        pass

    def initialize(self, **kwargs):
        pass

    def get_inventory(self, context):
        """  """

        with LoggingSessionContext(context) as logger:
            resource_config = ShellResource.create_from_context(context)

            logger.info("Configuration Templates Location: {path}"
                        "Username: {username}\n"
                        "Password: {password}\n"
                        "Host: {host}\n"
                        "STD: {std_port}\n"
                        "UWM: {uwm_port}".format(path=resource_config.templates_path,
                                                 host=resource_config.address,
                                                 std_port=resource_config.std_port,
                                                 uwm_port=resource_config.uwm_port,
                                                 username=resource_config.username,
                                                 password=resource_config.password))

            if resource_config.templates_path and not os.path.exists(resource_config.templates_path):
                msg = "Wrong path provided for device configuration templates"
                logger.error("{msg}. Provided path: {path}".format(msg=msg, path=resource_config.templates_path))
                raise VIRLShellError(msg)

            virl_api = VIRL_API(host=resource_config.address,
                                std_port=resource_config.std_port,
                                uwm_port=resource_config.uwm_port,
                                username=resource_config.username,
                                password=resource_config.password)

            try:
                avail_networks = virl_api.get_all_avail_networks()
                if resource_config.mgmt_network not in avail_networks:
                    raise VIRLShellError("Provided Management Network <{mgmt_network}> doesn't exist. "
                                         "Available networks: {avail_networks}".format(
                        mgmt_network=resource_config.mgmt_network, avail_networks=avail_networks))
                # virl_api.health_check()
            except HTTPError as err:
                raise VIRLShellError("Can not connect to VIRL Server. Please, verify provided credentials."
                                     "Error: {}".format(err))

            return AutoLoadDetails([], [])

    def PrepareSandboxInfra(self, context, request, cancellation_context):
        """ Called by CloudShell Orchestration during the Setup process
        in order to populate information about the networking environment used by the sandbox

        :param context: ResourceRemoteCommandContext
        :param request: Actions to be performed to prepare the networking environment sent by CloudShell Server
        :param cancellation_context:
        :return:
        """

        with LoggingSessionContext(context) as logger:

            resource_config = ShellResource.create_from_context(context)
            resource_config.api.WriteMessageToReservationOutput(resource_config.reservation_id,
                                                                "Preparing Sandbox Connectivity...")

            logger.info(f"REQUEST: {request}")
            logger.info("Cloud Provider Name: {}".format(resource_config.name))

            r_id, reservation_details = get_reservation_details(api=resource_config.api,
                                                                reservation_id=resource_config.reservation_id,
                                                                cloud_provider_name=resource_config.name)

            logger.info("Initial Reservation <{res_id}> Details: {details}".format(res_id=r_id,
                                                                                   details=reservation_details))
            json_request = json.loads(request)

            vcn_action_id = ""
            subnet_dict = {}
            subnet_results = []

            for action in json_request["driverRequest"]["actions"]:
                if action["type"] == "prepareCloudInfra":
                    vcn_action_id = action.get("actionId")
                elif action["type"] == "prepareSubnet":
                    subnet_action_id = action.get("actionId")
                    subnet_cidr = action.get("actionParams", {}).get("cidr")
                    subnet_alias = action.get("actionParams", {}).get("alias")
                    subnet_dict[subnet_cidr] = (subnet_action_id, subnet_alias)
                elif action["type"] == "createKeys":
                    keys_action_id = action.get("actionId")

            prepare_network_result = PrepareCloudInfraResult(vcn_action_id)

            virl_api = VIRL_API(host=resource_config.address,
                                std_port=resource_config.std_port,
                                uwm_port=resource_config.uwm_port,
                                username=resource_config.username,
                                password=resource_config.password)

            avail_image_types = virl_api.get_available_image_types()

            default_gateway_info = virl_api.get_default_gateway()

            # resources = {}
            for res_name, res_params in reservation_details["resources"].items():
                image_type = res_params.get("image type")
                if image_type not in avail_image_types:
                    raise VIRLShellError(f"Unable to find requested Image Type {image_type}>. "
                                         f"Avail images: {avail_image_types}")

                # NX-OS hack with IP address determination
                # if image_type in self.NEED_IP_ADDRESS:
                # res_params["ip address"] = virl_api.get_dhcp_ipaddr(network_name=resource_config.mgmt_network)
                # resources.update({res_name: res_params})

            # res_details.update({"resources": resources, "default_gateway_info": default_gateway_info})
            reservation_details.update({"default_gateway_info": default_gateway_info})

            logger.info(f"Updated Reservation Details: {reservation_details}")

            topology = Topology(**reservation_details)
            topology_data = topology.create_topology(mgmt_net_name=resource_config.mgmt_network,
                                                     template_path=resource_config.templates_path)

            logger.info(f"Topology Data: {topology_data}")

            virl_api.upload_topology(topology_data=topology_data, reservation_id=resource_config.reservation_id)
            ifaces_info = virl_api.get_ifaces_info(topology_name=resource_config.reservation_id)

            for subnet_action_cidr, (subnet_action_id, alias) in subnet_dict.items():
                logger.info(f"ACTIONS: {subnet_action_id}, {alias}, {subnet_action_cidr}")
                action_id = None

                if alias == "DefaultSubnet":
                    action_id = subnet_action_id
                    subnet_id = resource_config.mgmt_network
                else:
                    for connection in reservation_details.get("connections", []):
                        logger.info(
                            "ACTION CIDR: {}, CONN NETWORK: {}".format(subnet_action_cidr, connection.get("network")))
                        if connection.get("network") == subnet_action_cidr:
                            action_id = subnet_action_id
                            break
                    if not action_id and subnet_action_cidr in reservation_details.get("subnets", {}).values():
                        action_id = subnet_action_id
                    # else:
                    if not action_id:
                        raise VIRLShellError(f"Couldn't find appropriate network for action id {subnet_action_id}")

                    subnet_id = None
                    for _, node_params in ifaces_info.items():
                        for node in node_params:
                            address = node.get("ipv4")

                            if address and ipaddress.ip_address(address) in ipaddress.ip_network(subnet_action_cidr):
                                subnet_id = node.get("network")
                                break
                        if subnet_id:
                            break

                subnet_result = PrepareSubnetActionResult()
                subnet_result.actionId = action_id
                subnet_result.subnetId = subnet_id
                subnet_result.infoMessage = "Success"
                subnet_results.append(subnet_result)

            prepare_network_result.infoMessage = "PrepareConnectivity finished successfully"

            create_key_result = CreateKeysActionResult(actionId=keys_action_id, infoMessage="", accessKey="")

            results = [prepare_network_result, create_key_result]
            results.extend(subnet_results)

            result = DriverResponse(results).to_driver_response_json()
            logger.info(f"Prepare result {result}")
            return result

    def Deploy(self, context, request=None, cancellation_context=None):
        """  """

        actions = self.request_parser.convert_driver_request_to_actions(request)
        resource_config = ShellResource.create_from_context(context)
        # resource_config.api.WriteMessageToReservationOutput(context.reservation.reservation_id,
        #                                                     'Request JSON: ' + request)
        with LoggingSessionContext(context) as logger:

            deploy_action = None
            subnet_actions = list()
            for action in actions:
                if isinstance(action, DeployApp):
                    deploy_action = action
                if isinstance(action, ConnectSubnet):
                    subnet_actions.append(action)

            if deploy_action:

                deployment_name = deploy_action.actionParams.deployment.deploymentPath
                try:
                    deploy_method = next(self.deployments[deployment] for deployment in self.deployments.keys() if
                                         deployment_name.endswith(deployment))
                except StopIteration:
                    raise VIRLShellError("Could not find the deployment " + deployment_name)
                results = deploy_method(resource_config, logger, deploy_action, subnet_actions, cancellation_context)
                logger.info("Deploy result {}".format(DriverResponse(results).to_driver_response_json()))
                return DriverResponse(results).to_driver_response_json()
            else:
                raise VIRLShellError("Failed to deploy VM")

    def vm_from_image(self, resource_config, logger, deploy_action, subnet_actions, cancellation_context):
        """
        :param logger:
        :param resource_config:
        :param deploy_action:
        :param cancellation_context:
        :return:
        :type subnet_actions: list<ConnectSubnet>
        """
        # Init CloudShell and OCI APIs
        logger.info("Starting Deployment from Image")
        network_results = []

        # Read deployment attributes
        app_name = deploy_action.actionParams.appName
        vm_instance_details = InstanceDetails(deploy_action=deploy_action,
                                              api=resource_config.api)

        virl_api = VIRL_API(host=resource_config.address,
                            std_port=resource_config.std_port,
                            uwm_port=resource_config.uwm_port,
                            username=resource_config.username,
                            password=resource_config.password)

        # node_status = virl_api.get_nodes_status(topology_name=resource_config.reservation_id).get(app_name, {})
        nodes_status = virl_api.get_nodes_status(topology_name=resource_config.reservation_id)

        node_status = {}
        for node_name, node_info in nodes_status.items():
            if node_name.startswith("{app_name}-{res_id}".format(app_name=app_name.replace(" ", "-"),
                                                                 res_id=resource_config.reservation_id[-2:])):
                app_name = node_name
                node_status = node_info
                break

        logger.info(f"NODE Status: {node_status}")

        if vm_instance_details.autostart == "True":
            timeout = 0
            while not node_status.get("is_reachable", False) and timeout < int(vm_instance_details.startup_timeout):
                if node_status.get("is_reachable", False) is not None:
                    logger.info(f"Try to reboot Management interface for node <{app_name}>")
                    virl_api.reboot_mgmt_port(topology_name=resource_config.reservation_id, node_name=app_name)
                    t = IFACE_REBOOT_TIMEOUT
                else:
                    t = 0
                time.sleep(MIN_STARTUP_TIMEOUT - t)  # Decrease interface reboot timeout
                timeout += MIN_STARTUP_TIMEOUT
                logger.info(f"App Name: {app_name}")
                node_status = virl_api.get_nodes_status(topology_name=resource_config.reservation_id).get(app_name, {})
                logger.info(f"NODE Status: {node_status}")

            if not node_status.get("is_reachable", False):
                msg = "{app_name} can't changes state to REACHABLE. " \
                      "Please, verify node configuration using next params: " \
                      "Console Server: {console_server} " \
                      "Console Port: {console_port}".format(app_name=app_name,
                                                            console_server=node_status.get("console_server"),
                                                            console_port=node_status.get("console_port"))
                logger.warning(msg)
                resource_config.api.WriteMessageToReservationOutput(resource_config.reservation_id, f"Warning, {msg}")

        for vnic_action in subnet_actions:
            network_results.append(ConnectToSubnetActionResult(actionId=vnic_action.actionId))

        attributes = [Attribute("User", vm_instance_details.user),
                      Attribute("Password", vm_instance_details.password),
                      Attribute("Enable Password", vm_instance_details.enable_password),
                      Attribute("SNMP Read Community", vm_instance_details.snmp_community),
                      Attribute("Console Server IP Address", node_status.get("console_server")),
                      Attribute("Console Port", node_status.get("console_port"))]

        ifaces_info = virl_api.get_ifaces_info(topology_name=resource_config.reservation_id)
        logger.info(f"Interface info: {ifaces_info}")

        deploy_result = DeployAppResult(actionId=deploy_action.actionId,
                                        infoMessage="Deployment Completed Successfully",
                                        vmUuid=app_name,
                                        vmName=app_name,
                                        deployedAppAddress=node_status.get("mgmt_ip"),  # mgmt ip
                                        deployedAppAttributes=attributes,  # during generation resource
                                        vmDetailsData=create_vm_details(vm_name=app_name,
                                                                        mgmt_network=resource_config.mgmt_network,
                                                                        node_type=vm_instance_details.image_type,
                                                                        node_ifaces=ifaces_info.get(app_name, [])
                                                                        )
                                        )
        if cancellation_context.is_cancelled:
            return "Deployment cancelled and deleted successfully"

        action_results = [deploy_result]
        action_results.extend(network_results)
        return action_results

    def console(self, context, ports):
        """Generates a command for a console access to an instance"""
        resource_config = ShellResource.create_from_context(context)

        with LoggingSessionContext(context) as logger:
            instance_id = resource_config.remote_instance_id
            virl_api = VIRL_API(host=resource_config.address,
                                std_port=resource_config.std_port,
                                uwm_port=resource_config.uwm_port,
                                username=resource_config.username,
                                password=resource_config.password)

            # node_status = virl_api.get_nodes_status(topology_name=resource_config.reservation_id).get(app_name, {})
            nodes_status = virl_api.get_nodes_status(topology_name=resource_config.reservation_id)
            node_status = nodes_status.get(instance_id, {})
            ip = node_status.get("console_server")
            port = node_status.get("console_port")
            return f"Console IP and port are:\n{ip}:{port}\n"

    def DeleteInstance(self, context, ports):
        """ Delete a VM
        :param context: ResourceRemoteCommandContext
        :param ports: sub-resources to delete
        :return:
        """

        pass
        # # Code to delete instance based on remote command context
        # resource_config = ShellResource.create_from_context(context)
        # oci_ops = OciOps(resource_config)
        # oci_ops.compute_ops.terminate_instance()
        # name = context.remote_endpoints[0].fullname.split('/')[0]
        #
        # return "Successfully terminated instance " + name

    def remote_refresh_ip(self, context, cancellation_context, ports):
        """ Refresh the IP of the resource from the VM """

        resource_config = ShellResource.create_from_context(context)

        with resource_config.get_logger() as logger:
            virl_api = VIRL_API(host=resource_config.address,
                                std_port=resource_config.std_port,
                                uwm_port=resource_config.uwm_port,
                                username=resource_config.username,
                                password=resource_config.password)

            nodes_info = virl_api.get_nodes_info(topology_name=resource_config.reservation_id,
                                                 network_name=resource_config.mgmt_network)

            node_name = context.remote_endpoints[0].fullname.split('/')[0]
            resource_config.api.UpdateResourceAddress(node_name, nodes_info.get(node_name, ""))

    def PowerOff(self, context, ports):
        """ Power Off the VM represented by the resource
        :param context: ResourceRemoteCommandContext
        :param list[string] ports: the ports of the connection between the remote resource and the local resource, NOT IN USE!!!

        """

        resource_config = ShellResource.create_from_context(context)
        with resource_config.get_logger() as logger:
            name = context.remote_endpoints[0].fullname.split('/')[0]

            virl_api = VIRL_API(host=resource_config.address,
                                std_port=resource_config.std_port,
                                uwm_port=resource_config.uwm_port,
                                username=resource_config.username,
                                password=resource_config.password)

            virl_api.stop_node(topology_name=resource_config.reservation_id,
                               node_name=name)

            resource_config.api.SetResourceLiveStatus(name, "Offline", "Resource is powered off")

        return "VM stopped successfully"

    # the name is by the Qualisystems conventions
    def PowerOn(self, context, ports):
        """ Powers ON the remote VM

        :param ResourceRemoteCommandContext context: the context the command runs on
        :param list[string] ports: the ports of the connection between the remote resource and the local resource, NOT IN USE!!!
        """

        resource_config = ShellResource.create_from_context(context)
        with resource_config.get_logger() as logger:
            name = context.remote_endpoints[0].fullname.split('/')[0]
            virl_api = VIRL_API(host=resource_config.address,
                                std_port=resource_config.std_port,
                                uwm_port=resource_config.uwm_port,
                                username=resource_config.username,
                                password=resource_config.password)

            virl_api.start_node(topology_name=resource_config.reservation_id,
                                node_name=name)

            resource_config.api.SetResourceLiveStatus(name, "Online", "Resource is powered on")

        return "VM started  successfully"

    # the name is by the Qualisystems conventions
    def PowerCycle(self, context, ports, delay):
        """ Perform PowerOff followed up by PowerOn after {delay} seconds - NOT IN USE

        :param context: ResourceRemoteCommandContext
        :param ports: list[string] ports: the ports of the connection between the remote resource and the local resource, NOT IN USE!!!
        :param delay: int : Seconds to delay between powering off and back on.
        :return:
        """

        resource_config = ShellResource.create_from_context(context)
        output = self.PowerOff(context, ports)
        resource_config.api.WriteMessageToReservationOutput(resource_config.reservation_id, output)
        time.sleep(float(delay))
        output = self.PowerOn(context, ports)
        resource_config.api.WriteMessageToReservationOutput(resource_config.reservation_id, output)
        return

    def get_vm_uuid(self, context, vm_name):
        """
        :param context: ResourceRemoteCommandContext
        :param vm_name: full resource name of the resource
        :return: UID of the VM in OCI
        """

        resource_config = ShellResource.create_from_context(context)

        res_details = resource_config.api.GetResourceDetails(vm_name)
        return str(jsonpickle.encode(res_details.VmDetails.UID, unpicklable=False))

    def GetVmDetails(self, context, cancellation_context, requests):
        """ Return VM Details JSON to the Quali Server for refreshing the VM Details pane

        :param context: ResourceRemoteCommandContext
        :param cancellation_context: bool - will become True if action is cancelled
        :param requests: str JSON - requests for VMs to refresh
        :return:
        """

        with LoggingSessionContext(context) as logger:
            resource_config = ShellResource.create_from_context(context)
            virl_api = VIRL_API(host=resource_config.address,
                                std_port=resource_config.std_port,
                                uwm_port=resource_config.uwm_port,
                                username=resource_config.username,
                                password=resource_config.password)

            ifaces_info = virl_api.get_ifaces_info(topology_name=resource_config.reservation_id)
            logger.info(f"[GetVmDetails] IFACE INFO: {ifaces_info}")
            nodes_info = virl_api.get_nodes_status(topology_name=resource_config.reservation_id)
            logger.info(f"[GetVmDetails] NODES INFO: {nodes_info}")

            vm_details_results = []
            for refresh_request in json.loads(requests)["items"]:
                vm_name = refresh_request["deployedAppJson"]["name"]
                vm_details_results.append(create_vm_details(vm_name=vm_name,
                                                            mgmt_network=resource_config.mgmt_network,
                                                            node_type=nodes_info.get(vm_name, {}).get("node_type", ""),
                                                            node_ifaces=ifaces_info.get(vm_name, [])
                                                            ))
            return str(jsonpickle.encode(vm_details_results, unpicklable=False))

    def CleanupSandboxInfra(self, context, request):
        """

        :param context:
        :param request:
        :return:
        """

        json_request = json.loads(request)
        resource_config = ShellResource.create_from_context(context)
        cleanup_action_id = next(action["actionId"] for action in json_request["driverRequest"]["actions"] if
                                 action["type"] == "cleanupNetwork")

        with resource_config.get_logger() as logger:
            virl_api = VIRL_API(host=resource_config.address,
                                std_port=resource_config.std_port,
                                uwm_port=resource_config.uwm_port,
                                username=resource_config.username,
                                password=resource_config.password)

            if resource_config.reservation_id in virl_api.get_topologies_list():
                virl_api.stop_topology(topology_name=resource_config.reservation_id)

        cleanup_result = ActionResultBase("cleanupNetwork", cleanup_action_id)

        while resource_config.reservation_id in virl_api.get_topologies_list():
            time.sleep(30)

        return str(jsonpickle.encode({'driverResponse': {'actionResults': [cleanup_result]}},
                                     unpicklable=False))
