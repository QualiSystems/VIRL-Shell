#!/usr/bin/python
# -*- coding: utf-8 -*-

from cloudshell.shell.core.session.cloudshell_session import CloudShellSessionContext
from cloudshell.shell.core.session.logging_session import LoggingSessionContext


class VIRLShellDriverResource(object):
    def __init__(self, name, context):

        self.address = None
        self.attributes = {}
        self.resources = {}
        self._context = context
        self._cloudshell_model_name = "VIRL Shell 2G"
        self._name = name

    @classmethod
    def create_from_context(cls, context):
        """ Creates an instance of VIRL by given context """

        result = VIRLShellDriverResource(name=context.resource.name, context=context)
        result.address = context.resource.address

        for attr in context.resource.attributes:
            result.attributes[attr] = context.resource.attributes[attr]

        return result

    @property
    def api(self):
        return CloudShellSessionContext(self._context).get_api()

    @property
    def reservation_id(self):
        if hasattr(self._context, "remote_reservation"):
            reservation = self._context.remote_reservation
        else:
            reservation = self._context.reservation
        return reservation.reservation_id

    @property
    def tags(self):
        if hasattr(self._context, "remote_reservation"):
            reservation = self._context.remote_reservation
        else:
            reservation = self._context.reservation
        return {
            "CreatedBy": "Cloudshell",
            "ReservationId": reservation.reservation_id,
            "Owner": reservation.owner_user,
            "Domain": reservation.domain,
            "Blueprint": reservation.environment_name
        }

    def get_logger(self):
        return LoggingSessionContext(self._context)

    @property
    def remote_instance_id(self):
        """ Retrieve UID of the VM the resource represents
        :return:
        """

        endpoint = self._context.remote_endpoints[0].fullname.split("/")[0]
        parent_connected_resource = self.api.GetResourceDetails(endpoint)
        try:
            instance_id = [attribute.Value for attribute in parent_connected_resource.ResourceAttributes if
                           attribute.Name == "VM_UUID"][0]
        except Exception:
            instance_id = parent_connected_resource.VmDetails.UID
        return instance_id

    @property
    def username(self):
        """ Get VIRL API username """

        return self.attributes.get("{}.API User".format(self._cloudshell_model_name), None)

    @username.setter
    def username(self, value):
        """ Set VIRL API username """

        self.attributes["{}.API User".format(self._cloudshell_model_name)] = value

    @property
    def password(self):
        """ Get VIRL API password """

        password = self.attributes.get("{}.API Password".format(self._cloudshell_model_name), None)
        return self.api.DecryptPassword(password).Value if password else None

    @password.setter
    def password(self, value):
        """ Set VIRL API password """

        self.attributes["{}.API Password".format(self._cloudshell_model_name)] = value

    @property
    def std_port(self):
        """ Get VIRL STD API port """

        return self.attributes.get("{}.STD API Port".format(self._cloudshell_model_name), None)

    @std_port.setter
    def std_port(self, value):
        """ Set VIRL STD API port """

        self.attributes["{}.STD API Port".format(self._cloudshell_model_name)] = value

    @property
    def uwm_port(self):
        """ Get VIRL UWM API port """

        return self.attributes.get("{}.UWM API Port".format(self._cloudshell_model_name), None)

    @uwm_port.setter
    def uwm_port(self, value):
        """ Set VIRL UWM API port """

        self.attributes["{}.UWM API Port".format(self._cloudshell_model_name)] = value

    @property
    def mgmt_network(self):
        """ Get management network """

        return self.attributes.get("{}.Management Network".format(self._cloudshell_model_name), None)

    @mgmt_network.setter
    def mgmt_network(self, value):
        """ Set management network """

        self.attributes["{}.Management Network".format(self._cloudshell_model_name)] = value

    @property
    def templates_path(self):
        """ Get path where device configuration templates stored """

        return self.attributes.get("{}.Configuration Templates Location".format(self._cloudshell_model_name), None)

    @templates_path.setter
    def templates_path(self, value):
        """ Set path where device configuration templates stored """

        self.attributes["{}.Configuration Templates Location".format(self._cloudshell_model_name)] = value

    @property
    def name(self):
        """  """

        return self._name

    @name.setter
    def name(self, value):
        """  """

        self._name = value

    @property
    def cloudshell_model_name(self):
        """  """

        return self._cloudshell_model_name

    @cloudshell_model_name.setter
    def cloudshell_model_name(self, value):
        """  """

        self._cloudshell_model_name = value
