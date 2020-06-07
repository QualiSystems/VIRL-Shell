#!/usr/bin/python

import json
import uuid

from virl_exceptions import VIRLShellError

STARTUP_TIMEOUT_KEY = "startup timeout"
DEPLOYMENT_ATTRS = ["image type", "autostart", STARTUP_TIMEOUT_KEY]
MIN_STARTUP_TIMEOUT = 30  # seconds
APP_ATTRS = ["User", "Password", "Enable Password"]


def get_reservation_details(api, reservation_id, cloud_provider_name):
    """ Determine reservation details needed for correct VIRL deployment process """

    details = api.GetReservationDetails(reservationId=reservation_id, disableCache=True).ReservationDescription

    if details.Id != reservation_id:
        raise VIRLShellError("Wrong reservation details obtained")

    virl_resources = {}
    # edit_apps_requests = []
    app_names_mapping = {}
    for app in details.Apps:
        params = {}
        is_virl_app = False
        for deploy_path in app.DeploymentPaths:
            if deploy_path.DeploymentService.CloudProvider != cloud_provider_name:
                continue
            else:
                is_virl_app = True

            for attr in deploy_path.DeploymentService.Attributes:
                attr_name = attr.Name.split(".")[-1].lower()
                if attr_name in DEPLOYMENT_ATTRS:
                    if attr_name == STARTUP_TIMEOUT_KEY and int(attr.Value) < MIN_STARTUP_TIMEOUT:
                        params.update({attr_name: MIN_STARTUP_TIMEOUT})
                    else:
                        params.update({attr_name: attr.Value})
            break  # in case we have same CP for a few Deployment Paths

        if not is_virl_app:
            continue  # Application deployed with an another CP( not VIRL CP)

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

        new_app_name = "{app_name}-{res_id}-{uniq_id}".format(app_name=app.Name.replace(" ", "-"),
                                                              res_id=reservation_id[-2:],
                                                              uniq_id=uuid.uuid4().hex[:4])

        app_names_mapping.update({app.Name: new_app_name})
        # edit_apps_requests.append(ApiEditAppRequest(app.Name, new_app_name, None, None, None))

        virl_resources.update({new_app_name: params})
        # virl_resources.update({app.Name: params})

    # api.EditAppsInReservation(reservationId=reservation_id,
    #                           editAppsRequests=edit_apps_requests)

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
        source = app_names_mapping.get(connector.Source, connector.Source)
        target = app_names_mapping.get(connector.Target, connector.Target)

        if connector.Attributes:
            # between apps
            for attr in connector.Attributes:
                if attr.Name == "Selected Network":
                    network = json.loads(attr.Value).get("cidr")
                    connections.append({"src": source, "dst": target, "network": network})
                    break
        elif source in subnets:
            connections.append({"src": source, "dst": target, "network": subnets[source]})
        elif target in subnets:
            connections.append({"src": source, "dst": target, "network": subnets[target]})

    return details.Id, {"resources": virl_resources, "connections": connections, "subnets": subnets}
