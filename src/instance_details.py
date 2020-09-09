#!/usr/bin/python
# -*- coding: utf-8 -*-


class InstanceDetails(object):
    def __init__(self, deploy_action, api):
        self.api = api
        self._deployment_path = deploy_action.actionParams.deployment.deploymentPath
        self._deploy_attribs = deploy_action.actionParams.deployment.attributes
        self._app_resource = deploy_action.actionParams.appResource.attributes

    @property
    def image_type(self):
        return self._deploy_attribs.get("{}.Image Type".format(self._deployment_path), "")

    @property
    def autostart(self):
        return self._deploy_attribs.get("{}.AutoStart".format(self._deployment_path), "")

    @property
    def startup_timeout(self):
        return self._deploy_attribs.get("{}.StartUp Timeout".format(self._deployment_path), "")

    @property
    def additional_interfaces(self):
        return self._deploy_attribs.get("{}.Additional Interfaces".format(self._deployment_path), "")

    @property
    def user(self):
        return self._app_resource.get("User")

    @property
    def password(self):
        res_password = self._app_resource.get("Password", "")
        if res_password:
            return self.api.DecryptPassword(res_password).Value

        return res_password

    @property
    def enable_password(self):

        res_password = self._app_resource.get("Enable Password", "")
        if res_password:
            return self.api.DecryptPassword(res_password).Value

        return res_password

    @property
    def snmp_community(self):
        return self._app_resource.get("SNMP Read Community", "quali")
