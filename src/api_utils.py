#!/usr/bin/python

import json
from cloudshell.api.cloudshell_api import CloudShellAPISession

STARTUP_TIMEOUT_KEY = "startup timeout"
DEPLOYMENT_ATTRS = ["image type", "autostart", STARTUP_TIMEOUT_KEY]
MIN_STARTUP_TIMEOUT = 30  # seconds
APP_ATTRS = ["User", "Password", "Enable Password"]


def get_reservation_details(api, reservation_id, cloud_provider_name):
    """ Determine reservation details needed for correct VIRL deployment process """

    details = api.GetReservationDetails(reservationId=reservation_id, disableCache=True).ReservationDescription

    virl_resources = {}
    for app in details.Apps:
        params = {}
        for deploy_path in app.DeploymentPaths:
            if deploy_path.DeploymentService.CloudProvider != cloud_provider_name:
                continue
            for attr in deploy_path.DeploymentService.Attributes:
                attr_name = attr.Name.split(".")[-1].lower()
                if attr_name in DEPLOYMENT_ATTRS:
                    if attr_name == STARTUP_TIMEOUT_KEY and int(attr.Value) < MIN_STARTUP_TIMEOUT:
                        params.update({attr_name: MIN_STARTUP_TIMEOUT})
                    else:
                        params.update({attr_name: attr.Value})
            break  # in case we have same CP for a few Deployment Paths

        for attr in app.LogicalResource.Attributes:
            if attr.Name in APP_ATTRS:
                params.update({attr.Name: attr.Value})

        if "User" not in params:
            params.update({"User": "admin"})

        if "Password" not in params:
            params.update({"Password": "admin"})
        else:
            params.update({"Password": api.DecryptPassword(params.get("Password")).Value})

        if "Enable Password" not in params:
            params.update({"Enable Password": params.get("Password", "")})
        else:
            params.update({"Enable Password": api.DecryptPassword(params.get("Enable Password")).Value})
        virl_resources.update({app.Name: params})

    subnets = {}
    services = details.Services
    for service in services:
        if service.ServiceName == "Subnet":
            network = None
            for attr in service.Attributes:
                if attr.Name == "Allocated CIDR":
                    network = attr.Value
                    break
            subnets.update({service.Alias: network})

    connections = []
    connectors = details.Connectors
    for connector in connectors:
        if connector.Attributes:
            # between apps
            for attr in connector.Attributes:
                if attr.Name == "Selected Network":
                    network = json.loads(attr.Value).get("cidr")
                    connections.append({"src": connector.Source, "dst": connector.Target, "network": network})
                    break
        elif connector.Source in subnets:
            connections.append({"src": connector.Source, "dst": connector.Target, "network": subnets[connector.Source]})
        elif connector.Target in subnets:
            connections.append({"src": connector.Source, "dst": connector.Target, "network": subnets[connector.Target]})

    return details.Id, {"resources": virl_resources, "connections": connections, "subnets": subnets}


if __name__ == "__main__":
    HOST = "192.168.85.22"
    USERNAME = "admin"
    PASSWORD = "admin"
    DOMAIN = "Global"

    RES_ID = "3e384d29-d6fd-455c-9e5c-6bc0bc0d0e68"
    api = CloudShellAPISession(host=HOST,
                               username=USERNAME,
                               password=PASSWORD,
                               domain=DOMAIN)

    details = get_reservation_details(api=api, reservation_id=RES_ID, cloud_provider_name="VIRL")

    print("FINISH")
