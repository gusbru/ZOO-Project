#
# Author : Blasco Brauzzi, Fabrice Brito, Frank Löschau
#
# Copyright 2023 Terradue. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including with
# out limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import os

try:
    import zoo
except ImportError:
    print("Not running in zoo instance, using ZooStub object for testing")

    class ZooStub(object):
        def __init__(self):
            self.SERVICE_SUCCEEDED = 3
            self.SERVICE_FAILED = 4
            self.SERVICE_DEPLOYED = 6

        def update_status(self, conf, progress):
            print(f"Status {progress}")

        def _(self, message):
            print(f"invoked _ with {message}")

    conf = {}
    conf["lenv"] = {"message": ""}
    zoo = ZooStub()
    pass

from cookiecutter.main import cookiecutter
import sys
import shutil
import json
from pathlib import Path
import sys
from deploy_util import Process
import yaml
import requests
import botocore
from urllib.parse import urlparse
from collections import namedtuple
import os


def get_s3_settings():
    # you can extend this method to get the S3 credentials 
    return namedtuple(
        "S3Settings",
        ["region_name", "endpoint_url", "aws_access_key_id", "aws_secret_access_key"],
        defaults=[
            os.getenv("S3_REGION"),
            os.getenv("SERVICE_URL"),
            os.getenv("S3_ACCESS_KEY"),
            os.getenv("S3_SECRET_KEY"),
        ],
    )


class DeployService(object):
    def __init__(self, conf, inputs, outputs):

        self.conf = conf
        self.inputs = inputs
        self.outputs = outputs

        self.zooservices_folder = self.get_zoo_services_folder()

        self.cookiecutter_configuration_file = self._get_conf_value(
            key="configurationFile", section="cookiecutter"
        )
        self.cookiecutter_templates_folder = self._get_conf_value(
            key="templatesPath", section="cookiecutter"
        )
        self.cookiecutter_template_url = self._get_conf_value(
            key="templateUrl", section="cookiecutter"
        )

        self.cookiecutter_template_branch = self._get_conf_value_if_exists(
            key="templateBranch", section="cookiecutter"
        )

        self.tmp_folder = self._get_conf_value("tmpPath")

        self.process_id = self.conf["lenv"]["usid"]

        self.service_tmp_folder = self.create_service_tmp_folder()

        self.cwl_content = self.get_application_package()

        if "workflow_id" in self.conf["lenv"]:
            self.service_configuration = Process.create_from_cwl(self.cwl_content,self.conf["lenv"]["workflow_id"])
        else:
            self.service_configuration = Process.create_from_cwl(self.cwl_content)

        self.service_configuration.service_provider = (
            f"{self.service_configuration.identifier}.service"
        )
        self.service_configuration.service_type = "Python"

        self.conf["lenv"]["workflow_id"] = self.service_configuration.identifier
        self.conf["lenv"]["service_name"] = self.service_configuration.identifier

    def get_zoo_services_folder(self):

        # checking for namespace
        if "zooServicesNamespace" in self.conf and \
                "namespace" in self.conf["zooServicesNamespace"] and \
                "servicesNamespace" in self.conf and \
                "path" in self.conf["servicesNamespace"]:
            zooservices_folder = os.path.join(self.conf["servicesNamespace"]["path"],
                                              self.conf["zooServicesNamespace"]["namespace"])
        else:
        # if no namespace is used, we will use the default services path
            print(self.conf["renv"], file=sys.stderr)
            zooservices_folder = self._get_conf_value(
                key="CONTEXT_DOCUMENT_ROOT", section="renv"
            )

        # Checking if zoo can write in the servicePath
        self.check_write_permissions(zooservices_folder)

        return zooservices_folder

    def _get_conf_value(self, key, section="main"):

        print(section, file=sys.stderr)
        if key in self.conf[section].keys():
            return self.conf[section][key]
        else:
            raise ValueError(f"{key} not set, check configuration")

    def _get_conf_value_if_exists(self, key, section="main"):

        print(section, file=sys.stderr)
        if key in self.conf[section].keys():
            return self.conf[section][key]
        else:
            return None

    @staticmethod
    def check_write_permissions(folder):

        if not os.access(folder, os.W_OK):
            errorMsg = f"Cannot write to {folder}. Please check folder"
            print(errorMsg, file=sys.stderr)
            raise Exception(errorMsg)

    def create_service_tmp_folder(self):
        # creating the folder where we will download the applicationPackage
        tmp_path = os.path.join(self.tmp_folder, f"DeployProcess-{self.process_id}")
        try:
            os.makedirs(tmp_path)
        except Exception as e:
            print(e,file=sys.stderr)

        return tmp_path

    def get_application_package(self):

        # checking if applicationPackage exists
        if "applicationPackage" not in self.inputs.keys():
            raise ValueError("The inputs dot not include applicationPackage")

        # loading cwl in yaml object
        if "cache_file" in self.inputs["applicationPackage"]:
            cwl_content = yaml.safe_load(open(self.inputs["applicationPackage"]["cache_file"]).read())
        else:
            cwl_content = yaml.safe_load(self.inputs["applicationPackage"]["value"])

        return cwl_content

    def generate_service(self):

        path=None
        print(self.conf["lenv"],file=sys.stderr)
        if "noRunSql" in self.conf["lenv"]:
            # checking if the template location is remote or local
            if self.cookiecutter_template_url.endswith(".git"):

                template_folder = os.path.join(
                    self.cookiecutter_templates_folder,
                    Path(self.cookiecutter_template_url).stem,
                )

                # checking if template had already been cloned
                if os.path.isdir(template_folder):
                    shutil.rmtree(template_folder)

                # retrieving the branch to clone
                # if no branch is specified, we will clone the master branch
                cookiecutter_template_branch = self.cookiecutter_template_branch

                # cloning the template
                if cookiecutter_template_branch is not None:
                    os.system(
                        f"git clone -b {cookiecutter_template_branch} {self.cookiecutter_template_url} {template_folder}"
                    )
                else:
                    os.system(f"git clone {self.cookiecutter_template_url} {template_folder}")

            else:
                raise ValueError(
                    f"{self.cookiecutter_template_url} is not a valid git repo"
                )

            cookiecutter_values = {"service_name": self.service_configuration.identifier,
                                  "workflow_id": self.service_configuration.identifier,
                                  "conf": self.conf["cookiecutter"]}

            # Create project from template
            path = cookiecutter(
                template_folder,
                extra_context=cookiecutter_values,
                output_dir=self.service_tmp_folder,
                no_input=True,
                overwrite_if_exists=True,
                config_file=self.cookiecutter_configuration_file
            )

        if "metadb" not in self.conf:
            zcfg_file = os.path.join(
                self.zooservices_folder, f"{self.service_configuration.identifier}.zcfg"
            )
            with open(zcfg_file, "w") as file:
                self.service_configuration.write_zcfg(file)

        # checking if service had already been deployed previously
        # if yes, delete it before redeploy the new one
        old_service = os.path.join(self.zooservices_folder,self.service_configuration.identifier)
        if os.path.isdir(old_service):
            shutil.rmtree(old_service)
            if "metadb" not in self.conf:
                os.remove(zcfg_file)

        if "metadb" in self.conf and not("noRunSql" in self.conf["lenv"] and self.conf["lenv"]["noRunSql"] != "false"):
            rSql=self.service_configuration.run_sql(self.conf)
            if not(rSql):
                return False

        if path is not None:
            app_package_file = os.path.join(
                path,
                f"app-package.cwl",
            )

            with open(app_package_file, "w") as file:
                yaml.dump(self.cwl_content, file)

            shutil.move(path, self.zooservices_folder)

            shutil.rmtree(self.service_tmp_folder)

        self.conf["lenv"]["deployedServiceId"] = self.service_configuration.identifier

        return True

def duplicateMessage(conf,deploy_process):
    sLocation=conf["openapi"]["rootUrl"]+"/processes/"+deploy_process.service_configuration.identifier
    if "headers" in conf:
        conf["headers"]["Location"]=sLocation
    else:
        conf["headers"]={"Location": sLocation }
    conf["lenv"]["code"]="DuplicatedProcess"
    conf["lenv"]["message"]=zoo._("A service with the same identifier is already deployed")
    return zoo.SERVICE_FAILED

def DeployProcess(conf, inputs, outputs):
    try:
        print(f"conf = {json.dumps(conf, indent=4)}", file=sys.stderr)
        print(f"inputs = {json.dumps(inputs, indent=4)}", file=sys.stderr)
        print(f"outputs = {json.dumps(outputs, indent=4)}", file=sys.stderr)
        print(f"zoo.__file__ = {zoo.__file__}, file=sys.stderr")
        if "applicationPackage" in inputs.keys() and "isArray" in inputs["applicationPackage"].keys() and inputs["applicationPackage"]["isArray"]=="true":
            for i in range(int(inputs["applicationPackage"]["length"])):
                lInputs = {"applicationPackage": {"value": inputs["applicationPackage"]["value"][i]}}
                lInputs["applicationPackage"]["mimeType"] = inputs["applicationPackage"]["mimeType"][i]
                deploy_process = DeployService(conf, lInputs, outputs)
                res=deploy_process.generate_service()
                if not(res):
                    return duplicateMessage(conf,deploy_process)
        else:
            deploy_process = DeployService(conf, inputs, outputs)
            res=deploy_process.generate_service()
            if not(res):
                return duplicateMessage(conf,deploy_process)
        response_json = {
            "message": f"Service {deploy_process.service_configuration.identifier} version {deploy_process.service_configuration.version} successfully deployed.",
            "service": deploy_process.service_configuration.identifier,
            "status": "success"
        }
        outputs["Result"]["value"] = json.dumps(response_json)
        return zoo.SERVICE_DEPLOYED
    except Exception as e:
        print("Exception in Python service",file=sys.stderr)
        print(e,file=sys.stderr)
        conf["lenv"]["message"]=str(e)
        return zoo.SERVICE_FAILED


if __name__ == "__main__":
    conf = {
        "main": {
            "encoding": "utf-8",
            "version": "1.0.0",
            "serverAddress": "http://127.0.0.1",
            "language": "en-US",
            "lang": "fr-FR,en-CA,en-US",
            "tmpPath": "/tmp/zTmp",
            "tmpUrl": "https://zoo.mkube.dec.earthdaily.com/temp/",
            "mapserverAddress": "https://zoo.mkube.dec.earthdaily.com/cgi-bin/mapserv",
            "dataPath": "/usr/com/zoo-project",
            "cacheDir": "/tmp/zTmp",
            "templatesPath": "/var/www/",
            "search_path": "true",
            "executionType": "json",
            "rversion": "1.0.0",
            "extra_supported_codes": "201"
        },
        "identification": {
            "title": "ZOO-Project with Deploy, Replace, Undeploy and CWL support",
            "abstract_file": "/var/www/header.md",
            "fees": "None",
            "accessConstraints": "none",
            "keywords": "WPS,GIS,buffer"
        },
        "provider": {
            "providerName": "ZOO-Project",
            "providerSite": "http://www.zoo-project.org",
            "individualName": "Gerald FENOY",
            "positionName": "Developer",
            "role": "Dev",
            "addressDeliveryPoint": "1280, avenue des Platanes",
            "addressCity": "Lattes",
            "addressAdministrativeArea": "False",
            "addressPostalCode": "34970",
            "addressCountry": "fr",
            "addressElectronicMailAddress": "gerald.fenoy@geolabs.fr",
            "phoneVoice": "False",
            "phoneFacsimile": "False"
        },
        "env": {
            "PYTHONPATH": "/usr/miniconda3/envs/ades-dev/lib/python3.8/site-packages",
            "CONTEXT_DOCUMENT_ROOT": "/usr/lib/cgi-bin/",
            "SERVICES_NAMESPACE": "bob"
        },
        "database": {
            "dbname": "zoo",
            "port": "5432",
            "user": "zoo",
            "password": "zoo",
            "host": "zoo-project-dru-postgresql",
            "type": "PG",
            "schema": "public"
        },
        "metadb": {
            "dbname": "zoo",
            "port": "5432",
            "user": "zoo",
            "password": "zoo",
            "host": "zoo-project-dru-postgresql",
            "type": "PG",
            "schema": "public"
        },
        "security": {
            "attributes": "Authorization,Cookie,User-Agent",
            "hosts": "*"
        },
        "cookiecutter": {
            "configurationFile": "/tmp/zTmp/cookiecutter_config.yaml",
            "templatesPath": "/tmp/zTmp/cookiecutter-templates",
            "templateUrl": "https://github.com/gusbru/eoepca-proc-service-template.git",
            "templateBranch": "test2"
        },
        "servicesNamespace": {
            "path": "/opt/zooservices_user",
            "deploy_service_provider": "DeployProcess",
            "undeploy_service_provider": "UndeployProcess",
            "has_jwt_service": "true",
            "sections_list": "auth_env,additional_parameters,pod_env_vars,pod_node_selector,eoepca"
        },
        "eoepca": {
            "domain": "mkube.dec.earthdaily.com",
            "registration_api_url": "https://registration-api.mkube.dec.earthdaily.com",
            "resource_catalog_api_url": "https://resource-catalog.mkube.dec.earthdaily.com",
            "workspace_url": "https://workspace-api.mkube.dec.earthdaily.com",
            "workspace_prefix": "ws"
        },
        "headers": {
            "X-Powered-By": "ZOO-Project-DRU"
        },
        "rabbitmq": {
            "host": "zoo-project-dru-rabbitmq",
            "port": "5672",
            "user": "guest",
            "passwd": "guest",
            "exchange": "amq.direct",
            "routingkey": "zoo",
            "queue": "zoo_service_queue"
        },
        "server": {
            "async_worker": "70"
        },
        "openapi": {
            "use_content": "false",
            "rootUrl": "https://zoo.mkube.dec.earthdaily.com/ogc-api",
            "rootHost": "https://zoo.mkube.dec.earthdaily.com",
            "rootPath": "ogc-api",
            "links": "/,/api,/conformance,/processes,/jobs",
            "paths": "/root,/conformance,/api,/processes,/processes/water-bodies,/processes/{processID},/processes/water-bodies/execution,/processes/{processID}/execution,/jobs,/jobs/{jobID},/jobs/{jobID}/results",
            "parameters": "processID,jobID,resultID",
            "header_parameters": "oas-header1,oas-header2,oas-header3,oas-header4,oas-header5,limitParam,skipParam,processIdParam,statusParam,minDurationParam,maxDurationParam,typeParam,datetimeParam,wParam",
            "version": "3.0.3",
            "license_name": "OGC license",
            "license_url": "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/LICENSE",
            "full_html_support": "false",
            "partial_html_support": "false",
            "wsUrl": "wss://zoo.mkube.dec.earthdaily.com:8888/",
            "publisherUrl": "http://zookernel/cgi-bin/publish.py?jobid=",
            "link_href": "http://zoo-project.org/dl/link.json",
            "tags": "Browse the API,List - deploy - get detailed information about processes,Execute process - monitor job - access the result,Jobs management,Processes management,Other endpoints",
            "examplesPath": "/var/www/html/examples/",
            "examplesUrl": "https://zoo.mkube.dec.earthdaily.com/examples/",
            "exceptionsUrl": "http://www.opengis.net/def/rel/ogc/1.0/exception",
            "exceptionsUrl_1": "http://www.opengis.net/def/exceptions/ogcapi-processes-2/1.0",
            "use_problem_json_content_type_for_exception": "true"
        },
        "tags": {
            "length": "6",
            "value": "From the landing page we can list links exposed by the API, it should contains a link to `/conformance` to use to know what are the server capabilities.",
            "value_1": "From this section, we can list available processes, deploy new processes then get detailled description of the created process",
            "value_2": "From this section, we can execute processes to create jobs, monitor these jobs during their execution then access the resulting data",
            "value_3": "From this section, we can list or dismiss jobs",
            "value_4": "From this section, we can modify or remove deployed processes",
            "value_5": "From this section, we can access the process description and the execution endpoint for any processes"
        },
        "oas-header1": {
            "in": "header",
            "name": "Prefer",
            "type": "string",
            "required": "true",
            "enum": "return=representation,return=minimal,respond-async;return=representation",
            "enum1": "return=representation,return=minimal,respond-async;return=representation,respond-async;return=minimal"
        },
        "oas-header2": {
            "in": "header",
            "name": "Prefer",
            "type": "string",
            "required": "false",
            "enum": "return=representation,return=minimal"
        },
        "oas-header3": {
            "in": "header",
            "name": "Prefer",
            "type": "string",
            "required": "true",
            "enum": "respond-async;return=representation"
        },
        "oas-header4": {
            "in": "header",
            "name": "Prefer",
            "type": "string",
            "required": "true",
            "enum": "return=minimal"
        },
        "oas-header5": {
            "in": "header",
            "name": "Prefer",
            "type": "string",
            "required": "true",
            "enum": "return=representation"
        },
        "limitParam": {
            "name": "limit",
            "title": "The limit parameter",
            "abstract": "The limit parameter indicates the number of elements to return in an array",
            "in": "query",
            "type": "integer",
            "schema_minimum": "1",
            "schema_maximum": "10000",
            "schema_default": "1000",
            "required": "false"
        },
        "skipParam": {
            "name": "skip",
            "title": "The skip parameter",
            "abstract": "The skip parameter indicates the number of elements to skip before starting returning values in an array",
            "in": "query",
            "type": "integer",
            "schema_minimum": "0",
            "required": "false"
        },
        "wParam": {
            "name": "w",
            "title": "The workflow id parameter",
            "abstract": "The workflow parameter indicates the name of an existing entry point within the CWL workflow definition associated with",
            "in": "query",
            "type": "string",
            "schema_default": "water-bodies",
            "required": "false"
        },
        "/": {
            "rel": "self",
            "type": "application/json",
            "title": "this document"
        },
        "root": {
            "method": "get",
            "title": "landing page of this API",
            "abstract": "The landing page provides links to the API definition, the Conformance statements and the metadata about the processes offered by this service.",
            "tags": "Browse the API",
            "operationId": "get_root",
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/responses/LandingPage.yaml"
        },
        "/index.html": {
            "rel": "alternate",
            "type": "text/html"
        },
        "/api": {
            "rel": "service-desc",
            "type": "application/vnd.oai.openapi+json;version=3.0",
            "title": "the API definition"
        },
        "/api.html": {
            "rel": "service-doc",
            "type": "text/html"
        },
        "api.html": {
            "href": "https://zoo.mkube.dec.earthdaily.com/swagger-ui/oapip/"
        },
        "api": {
            "method": "get",
            "title": "This document",
            "abstract": "This document",
            "tags": "Browse the API",
            "operationId": "get_api"
        },
        "/conformance": {
            "rel": "http://www.opengis.net/def/rel/ogc/1.0/conformance",
            "type": "application/json",
            "title": "OGC API - Processes conformance classes implemented by this server"
        },
        "conformance": {
            "method": "get",
            "title": "information about standards that this API conforms to",
            "abstract": "List all conformance classes specified in the OGC API - Processes - Part 1: Core standard that the server conforms to",
            "tags": "Browse the API",
            "operationId": "get_conformance",
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/responses/ConformanceDeclaration.yaml"
        },
        "/conformance.html": {
            "rel": "alternate",
            "type": "text/html"
        },
        "/processes": {
            "rel": "http://www.opengis.net/def/rel/ogc/1.0/processes",
            "type": "application/json",
            "title": "The processes offered by this server"
        },
        "processes": {
            "length": "2",
            "method": "get",
            "title": "retrieve available processes",
            "abstract": "Information about the available processes",
            "abstract_file": "/var/www/processes-list.md",
            "tags": "List - deploy - get detailed information about processes",
            "parameters": "/components/parameters/limitParam,/components/parameters/skipParam",
            "schema": "https://raw.githubusercontent.com/GeoLabs/ogcapi-processes/rel-1.0/core/openapi/responses/ProcessList.yaml",
            "method_1": "post",
            "ecode_1": "500",
            "code_1": "201",
            "title_1": "deploy a new processes",
            "abstract_1": "Deploy a new processes",
            "abstract_file_1": "/var/www/deploy.md",
            "tags_1": "List - deploy - get detailed information about processes",
            "operationId_1": "post_processes",
            "parameters_1": "/components/parameters/wParam",
            "schema_1": "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/openapi/responses/processes-dru/rDeployProcess.yaml",
            "requestBody_length_1": "2",
            "requestBody_1_1": "requestBodyPkg",
            "examples_1_1": "app-package.json",
            "examples_summary_1_1": "Deploy water-bodies process using OGC Application Package encoding",
            "requestBody_1": "requestBodyCwl",
            "examples_ref_1": "https://raw.githubusercontent.com/EOEPCA/app-snuggs/main/app-package.cwl",
            "examples_1": "app-package.cwl",
            "examples_summary_1": "Deploy water-bodies process using the CWL Application Package encoding"
        },
        "/processes.html": {
            "rel": "alternate",
            "type": "text/html"
        },
        "processes/{processID}": {
            "prel": "http://www.opengis.net/def/rel/iana/1.0/describedby",
            "rel": "self",
            "length": "3",
            "method": "get",
            "ecode": "404",
            "title": "retrieve a process description",
            "abstract": "A process description.",
            "tags": "Other endpoints",
            "aoperationId": "get_process__processID__",
            "schema": "https://raw.githubusercontent.com/GeoLabs/ogcapi-processes/rel-1.0/core/openapi/responses/swagger/ProcessDescription.yaml",
            "parameters": "/components/parameters/processID",
            "method_1": "delete",
            "ecode_1": "404",
            "code_1": "204",
            "title_1": "undeploy a mutable process",
            "abstract_1": "Undeploy a mutable process.",
            "tags_1": "Processes management",
            "aoperationId_1": "delete_process__processID__",
            "parameters_1": "/components/parameters/processID",
            "method_2": "put",
            "ecode_2": "404",
            "code_2": "204",
            "aoperationId_2": "put_process__processID__",
            "title_2": "Update a mutable process",
            "requestBody_length_2": "2",
            "requestBody_2": "requestBodyPkg",
            "requestBody_2_1": "requestBodyCwl",
            "abstract_2": "Update a mutable process.",
            "tags_2": "Processes management",
            "parameters_2": "/components/parameters/processID",
            "examples_2": "app-package.json",
            "examples_summary_2": "Update water-bodies process",
            "examples_ref_2_1": "https://raw.githubusercontent.com/EOEPCA/app-snuggs/main/app-package.cwl",
            "examples_2_1": "app-package.cwl",
            "examples_summary_2_1": "Update test water-bodies process"
        },
        "processes/water-bodies": {
            "prel": "http://www.opengis.net/def/rel/iana/1.0/describedby",
            "pname": "water-bodies",
            "length": "1",
            "method": "get",
            "ecode": "404",
            "title": "Retrieve the water-bodies process description",
            "abstract": "The water-bodies process description.",
            "abstract_file": "/var/www/processes-description.md",
            "tags": "List - deploy - get detailed information about processes",
            "schema": "https://raw.githubusercontent.com/GeoLabs/ogcapi-processes/rel-1.0/core/openapi/responses/swagger/ProcessDescription.yaml",
            "aparameters": "/components/parameters/processID"
        },
        "processes/{processID}/execution": {
            "rel": "http://www.opengis.net/def/rel/ogc/1.0/execute",
            "length": "1",
            "ecode": "400,404,500",
            "method": "post",
            "title": "execute a job",
            "abstract": "An execute endpoint.",
            "tags": "Other endpoints",
            "operationId": "processes__processID__execution",
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/responses/ExecuteSync.yaml",
            "parameters": "/components/parameters/processID,/components/parameters/oas-header1",
            "requestBody": "requestBody",
            "callbacksReference": "callbacks"
        },
        "processes/water-bodies/execution": {
            "length": "1",
            "method": "post",
            "ecode": "400,404,500",
            "pname": "water-bodies",
            "title": "execute water-bodies",
            "abstract": "An execute endpoint.",
            "abstract_file": "/var/www/execute.md",
            "tags": "Execute process - monitor job - access the result",
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/responses/ExecuteSync.yaml",
            "parameters": "/components/parameters/oas-header3",
            "callbacksReference": "callbacks",
            "examples": "job-order1.json",
            "examples_summary": "Execute water-bodies with the presented stac item"
        },
        "/jobs": {
            "rel": "http://www.opengis.net/def/rel/ogc/1.0/job-list",
            "type": "application/json",
            "title": "Job Management"
        },
        "jobs": {
            "length": "1",
            "method": "get",
            "ecode": "500",
            "title": "retrieve a list of jobs run",
            "abstract": "A list of jobs run.",
            "tags": "Jobs management",
            "operationId": "get_jobs",
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/responses/JobList.yaml",
            "parameters": "/components/parameters/limitParam,/components/parameters/skipParam,/components/parameters/processIdParam,/components/parameters/statusParam,/components/parameters/minDurationParam,/components/parameters/maxDurationParam,/components/parameters/typeParam,/components/parameters/datetimeParam"
        },
        "requestBody": {
            "abstract": "Mandatory execute request in JSON format",
            "type": "application/json",
            "schema": "https://raw.githubusercontent.com/GeoLabs/ogcapi-processes/rel-1.0/core/openapi/schemas/execute.yaml"
        },
        "requestBodyPkg": {
            "abstract": "Mandatory OGC Application Package in JSON format",
            "type": "application/ogcapppkg+json",
            "schema": "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/openapi/schemas/processes-dru/ogcapppkg.yaml"
        },
        "requestBodyCwl": {
            "abstract": "Mandatory OGC Application Package in CWL format",
            "type": "application/cwl+yaml",
            "schema": "https://raw.githubusercontent.com/common-workflow-language/schema_salad/main/schema_salad/metaschema/metaschema.yml"
        },
        "/jobs.html": {
            "rel": "alternate",
            "type": "text/html"
        },
        "/jobs/{jobID}": {
            "rel": "canonical",
            "type": "application/json",
            "title": "Status"
        },
        "jobs/{jobID}": {
            "length": "2",
            "method": "get",
            "operationId": "get_jobs__jobID_",
            "ecode": "404,500",
            "title": "The status of a job.",
            "abstract": "The status of a job.",
            "abstract_file": "/var/www/job-status.md",
            "tags": "Execute process - monitor job - access the result",
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/responses/Status.yaml",
            "parameters": "/components/parameters/jobID",
            "method_1": "delete",
            "ecode_1": "404,500",
            "title_1": "Delete a job",
            "operationId_1": "delete_jobs__jobID__",
            "abstract_1": "Cancel the job execution.",
            "tags_1": "Jobs management",
            "schema_1": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/responses/Status.yaml",
            "parameters_1": "/components/parameters/jobID"
        },
        "/jobs/{jobID}/results": {
            "rel": "http://www.opengis.net/def/rel/ogc/1.0/results",
            "type": "application/json",
            "title": "Get Result"
        },
        "jobs/{jobID}/results": {
            "method": "get",
            "operationId": "get_jobs__jobID__results",
            "ecode": "404,500",
            "title": "The result of a job execution.",
            "abstract": "The result of a job execution.",
            "abstract_file": "/var/www/job-results.md",
            "tags": "Execute process - monitor job - access the result",
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/responses/Results.yaml",
            "parameters": "/components/parameters/jobID",
            "ep": ",/components/parameters/oas-header2"
        },
        "{processID}": {
            "type": "string",
            "title": "The id of a process",
            "abstract": "The id of a process",
            "in": "path",
            "required": "true",
            "example": "water-bodies"
        },
        "{jobID}": {
            "type": "string",
            "title": "The id of a job",
            "abstract": "The id of a job",
            "in": "path",
            "required": "true"
        },
        "{resultID}": {
            "type": "string",
            "title": "The id of an output",
            "abstract": "The id of an output",
            "in": "path",
            "required": "true"
        },
        "statusParam": {
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/parameters/status.yaml"
        },
        "processIdParam": {
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/parameters/processIdQueryParam.yaml"
        },
        "minDurationParam": {
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/parameters/minDuration.yaml"
        },
        "maxDurationParam": {
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/parameters/maxDuration.yaml"
        },
        "typeParam": {
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/parameters/type.yaml"
        },
        "datetimeParam": {
            "schema": "https://schemas.opengis.net/ogcapi/features/part1/1.0/openapi/parameters/datetime.yaml"
        },
        "{f}": {
            "default": "json",
            "enum": "json",
            "title": "The optional f parameter",
            "abstract": "The optional f parameter indicates the output format which the server shall provide as part of the response document.  The default format is JSON.",
            "in": "query",
            "required": "false"
        },
        "conformsTo": {
            "rootUrl": "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/",
            "extentionUrl": "http://www.opengis.net/spec/ogcapi-processes-2/1.0/conf/",
            "extentionUrl_1": "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/",
            "link": "core",
            "link_1": "oas30",
            "link_2": "json",
            "link_3": "job-list",
            "link_4": "dismiss",
            "link_5": "callback",
            "link_6": "ogc-process-description",
            "link_7": "deploy-replace-undeploy",
            "extention_7": "true",
            "extid_7": "0",
            "link_8": "ogcapppkg",
            "extention_8": "true",
            "extid_8": "0",
            "link_9": "cwl",
            "extention_9": "true",
            "extid_9": "0",
            "link_10": "core",
            "extention_10": "true",
            "extid_10": "1",
            "link_11": "landing-page",
            "extention_11": "true",
            "extid_11": "1",
            "link_12": "oas30",
            "extention_12": "true",
            "extid_12": "1",
            "link_13": "json",
            "extention_13": "true",
            "extid_13": "1",
            "length": "14"
        },
        "exception": {
            "abstract": "Exception",
            "type": "application/json",
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/responses/NotFound.yaml",
            "default_schema": "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/openapi/responses/common-core/rServerError.yaml"
        },
        "responses": {
            "length": "7",
            "code": "404",
            "schema": "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/openapi/responses/common-core/rNotFound.yaml",
            "type": "application/json",
            "title": "NotFound",
            "code_1": "500",
            "schema_1": "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/openapi/responses/common-core/rServerError.yaml",
            "type_1": "application/json",
            "title_1": "ServerError",
            "code_2": "400",
            "schema_2": "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/openapi/responses/common-core/rInvalidParameter.yaml",
            "type_2": "appliction/json",
            "title_2": "InvalidParameter",
            "code_3": "405",
            "schema_3": "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/core/openapi/responses/NotAllowed.yaml",
            "type_3": "appliction/json",
            "title_3": "NotAllowed",
            "code_4": "406",
            "schema_4": "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/core/openapi/responses/NotSupported.yaml",
            "type_4": "appliction/json",
            "title_4": "NotSupported",
            "code_5": "401",
            "schema_5": "https://raw.githubusercontent.com/ZOO-Project/ZOO-Project/master/thirds/openapi/responses/Unauthorized.yaml",
            "type_5": "appliction/json",
            "title_5": "Unauthorized",
            "code_6": "403",
            "schema_6": "https://raw.githubusercontent.com/ZOO-Project/ZOO-Project/master/thirds/openapi/responses/Forbidden.yaml",
            "type_6": "appliction/json",
            "title_6": "Forbidden"
        },
        "callbacks": {
            "length": "3",
            "state": "jobSuccess",
            "uri": "successUri",
            "schema": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/results.yaml",
            "type": "application/json",
            "title": "Results received successfully",
            "state_1": "jobInProgress",
            "uri_1": "inProgressUri",
            "schema_1": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/statusInfo.yaml",
            "type_1": "application/json",
            "title_1": "Status received successfully",
            "state_2": "jobFailed",
            "uri_2": "failedUri",
            "schema_2": "https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/exception.yaml",
            "type_2": "application/json",
            "title_2": "Exception received successfully"
        },
        "provider_alt": {
            "addressDeliveryPoint": "streetAddress",
            "addressCity": "addressLocality",
            "addressAdministrativeArea": "addressRegion",
            "addressPostalCode": "postalCode",
            "addressCountry": "addressCountry",
            "addressElectronicMailAddress": "email",
            "phoneVoice": "telephone",
            "phoneFacsimile": "faxNumber",
            "hoursOfService": "hoursAvailable",
            "contactInstructions": "contactOption"
        },
        "filter_in": {
            "path": "/usr/lib/cgi-bin",
            "service": "securityIn"
        },
        "filter_out": {
            "path": "/usr/lib/cgi-bin",
            "service": "securityOut"
        },
        "links_title": {
            "self": "View this document in JSON.",
            "alternate": "View the alternative version in HTML.",
            "service-desc": "View the service description.",
            "service-doc": "View service documentation.",
            "processes": "View the list of processes the API offers.",
            "results": "View the results of a process.",
            "status": "View the current status of a job execution.",
            "execute": "View the execution endpoint of a process.",
            "job-list": "View the list of job available on this server.",
            "conformance": "View the conformance classes that the link's context conforms to."
        },
        "lenv": {
            "ds_nb": "2",
            "usid": "7e65e196-0701-11ef-8b69-0242ac110035",
            "uusid": "7e65e196-0701-11ef-8b69-0242ac110035",
            "metapath": "",
            "no-headers": "true",
            "osid": "1715363099",
            "sid": "78",
            "status": "3",
            "cwd": "/opt/zooservices_user/bob",
            "message": "Inputs downloaded, nested processes execution finalized",
            "soap": "false",
            "secured_url": "false",
            "can_continue": "false",
            "oIdentifier": "DeployProcess",
            "Identifier": "DeployProcess",
            "json_user": "{\"exp\": 1714575246, \"iat\": 1714488846, \"jti\": \"60d6ecaa-fd29-46a3-b04a-6fdc36e9d549\", \"iss\": \"https://keycloak.mkube.dec.earthdaily.com/realms/master\", \"aud\": \"account\", \"sub\": \"c3c33ca9-97f7-459a-ae34-8cd02380218b\", \"typ\": \"Bearer\", \"azp\": \"ws-bob\", \"session_state\": \"7cb3820c-24e9-4c15-8f40-4c0191c4e804\", \"acr\": \"1\", \"allowed-origins\": [\"*\"], \"realm_access\": {\"roles\": [\"default-roles-master\", \"offline_access\", \"uma_authorization\"]}, \"resource_access\": {\"account\": {\"roles\": [\"manage-account\", \"manage-account-links\", \"view-profile\"]}, \"ws-bob\": {\"roles\": [\"uma_protection\"]}}, \"scope\": \"profile email\", \"sid\": \"7cb3820c-24e9-4c15-8f40-4c0191c4e804\", \"email_verified\": false, \"preferred_username\": \"bob\"}",
            "fpm_user": "bob",
            "fpm_cwd": "/opt/zooservices_user/bob",
            "filter_in": "true",
            "request_method": "POST",
            "workflow_id": "custom5",
            "jrequest": "{\"inputs\":{\"applicationPackage\":[{\"value\":\"cwlVersion: v1.0\\n$namespaces:\\n  s: https://schema.org/\\ns:softwareVersion: 1.4.1\\nschemas:\\n  - http://schema.org/version/9.0/schemaorg-current-http.rdf\\n$graph:\\n  - class: Workflow\\n    id: custom5\\n    label: Water bodies detection based on NDWI and otsu threshold\\n    doc: Water bodies detection based on NDWI and otsu threshold\\n    requirements:\\n      - class: ScatterFeatureRequirement\\n      - class: SubworkflowFeatureRequirement\\n    inputs:\\n      aoi:\\n        label: area of interest\\n        doc: area of interest as a bounding box\\n        type: string\\n      epsg:\\n        label: EPSG code\\n        doc: EPSG code\\n        type: string\\n        default: EPSG:4326\\n      stac_items:\\n        label: Sentinel-2 STAC items\\n        doc: list of Sentinel-2 COG STAC items\\n        type: string[]\\n      bands:\\n        label: bands used for the NDWI\\n        doc: bands used for the NDWI\\n        type: string[]\\n        default:\\n          - green\\n          - nir\\n    outputs:\\n      - id: stac\\n        outputSource:\\n          - node_stac/stac_catalog\\n        type: Directory\\n    steps:\\n      node_water_bodies:\\n        run: '#detect_water_body'\\n        in:\\n          item: stac_items\\n          aoi: aoi\\n          epsg: epsg\\n          bands: bands\\n        out:\\n          - detected_water_body\\n        scatter: item\\n        scatterMethod: dotproduct\\n      node_stac:\\n        run: '#stac'\\n        in:\\n          item: stac_items\\n          rasters:\\n            source: node_water_bodies/detected_water_body\\n        out:\\n          - stac_catalog\\n  - class: Workflow\\n    id: detect_water_body\\n    label: Water body detection based on NDWI and otsu threshold\\n    doc: Water body detection based on NDWI and otsu threshold\\n    requirements:\\n      - class: ScatterFeatureRequirement\\n    inputs:\\n      aoi:\\n        doc: area of interest as a bounding box\\n        type: string\\n      epsg:\\n        doc: EPSG code\\n        type: string\\n        default: EPSG:4326\\n      bands:\\n        doc: bands used for the NDWI\\n        type: string[]\\n      item:\\n        doc: STAC item\\n        type: string\\n    outputs:\\n      - id: detected_water_body\\n        outputSource:\\n          - node_otsu/binary_mask_item\\n        type: File\\n    steps:\\n      node_crop:\\n        run: '#crop'\\n        in:\\n          item: item\\n          aoi: aoi\\n          epsg: epsg\\n          band: bands\\n        out:\\n          - cropped\\n        scatter: band\\n        scatterMethod: dotproduct\\n      node_normalized_difference:\\n        run: '#norm_diff'\\n        in:\\n          rasters:\\n            source: node_crop/cropped\\n        out:\\n          - ndwi\\n      node_otsu:\\n        run: '#otsu'\\n        in:\\n          raster:\\n            source: node_normalized_difference/ndwi\\n        out:\\n          - binary_mask_item\\n  - class: CommandLineTool\\n    id: crop\\n    requirements:\\n      InlineJavascriptRequirement: {}\\n      EnvVarRequirement:\\n        envDef:\\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\\n          PYTHONPATH: /app\\n      ResourceRequirement:\\n        coresMax: 1\\n        ramMax: 512\\n    hints:\\n      DockerRequirement:\\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/crop:1.5.0\\n    baseCommand:\\n      - python\\n      - '-m'\\n      - app\\n    arguments: []\\n    inputs:\\n      item:\\n        type: string\\n        inputBinding:\\n          prefix: '--input-item'\\n      aoi:\\n        type: string\\n        inputBinding:\\n          prefix: '--aoi'\\n      epsg:\\n        type: string\\n        inputBinding:\\n          prefix: '--epsg'\\n      band:\\n        type: string\\n        inputBinding:\\n          prefix: '--band'\\n    outputs:\\n      cropped:\\n        outputBinding:\\n          glob: '*.tif'\\n        type: File\\n  - class: CommandLineTool\\n    id: norm_diff\\n    requirements:\\n      InlineJavascriptRequirement: {}\\n      EnvVarRequirement:\\n        envDef:\\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\\n          PYTHONPATH: /app\\n      ResourceRequirement:\\n        coresMax: 1\\n        ramMax: 512\\n    hints:\\n      DockerRequirement:\\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/norm_diff:1.5.0\\n    baseCommand:\\n      - python\\n      - '-m'\\n      - app\\n    arguments: []\\n    inputs:\\n      rasters:\\n        type: File[]\\n        inputBinding:\\n          position: 1\\n    outputs:\\n      ndwi:\\n        outputBinding:\\n          glob: '*.tif'\\n        type: File\\n  - class: CommandLineTool\\n    id: otsu\\n    requirements:\\n      InlineJavascriptRequirement: {}\\n      EnvVarRequirement:\\n        envDef:\\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\\n          PYTHONPATH: /app\\n      ResourceRequirement:\\n        coresMax: 1\\n        ramMax: 512\\n    hints:\\n      DockerRequirement:\\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/otsu:1.5.0\\n    baseCommand:\\n      - python\\n      - '-m'\\n      - app\\n    arguments: []\\n    inputs:\\n      raster:\\n        type: File\\n        inputBinding:\\n          position: 1\\n    outputs:\\n      binary_mask_item:\\n        outputBinding:\\n          glob: '*.tif'\\n        type: File\\n  - class: CommandLineTool\\n    id: stac\\n    requirements:\\n      InlineJavascriptRequirement: {}\\n      EnvVarRequirement:\\n        envDef:\\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\\n          PYTHONPATH: /app\\n      ResourceRequirement:\\n        coresMax: 1\\n        ramMax: 512\\n    hints:\\n      DockerRequirement:\\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/stac:1.5.0\\n    baseCommand:\\n      - python\\n      - '-m'\\n      - app\\n    arguments: []\\n    inputs:\\n      item:\\n        type:\\n          type: array\\n          items: string\\n          inputBinding:\\n            prefix: '--input-item'\\n      rasters:\\n        type:\\n          type: array\\n          items: File\\n          inputBinding:\\n            prefix: '--water-body'\\n    outputs:\\n      stac_catalog:\\n        outputBinding:\\n          glob: .\\n        type: Directory\",\"format\":{\"mediaType\":\"application/cwl\"}}]}}",
            "service_name": "custom5",
            "deployedServiceId": "custom5",
            "noRunSql": "true",
            "async": "true",
            "file.sid": "/tmp/zTmp/7e65e196-0701-11ef-8b69-0242ac110035.sid",
            "file.pid": "/tmp/zTmp/7e65e196-0701-11ef-8b69-0242ac110035.pid",
            "file.responseInit": "/tmp/zTmp/DeployProcess_7e65e196-0701-11ef-8b69-0242ac110035.json",
            "file.log": "/tmp/zTmp/DeployProcess_7e65e196-0701-11ef-8b69-0242ac110035_error.log",
            "file.responseFinal": "/tmp/zTmp/DeployProcess_final_7e65e196-0701-11ef-8b69-0242ac110035.json",
            "serviceType": "Python",
            "PercentCompleted": "3"
        },
        "zooServicesNamespace": {
            "namespace": "bob"
        },
        "auth_env": {
            "user": "bob",
            "cwd": "/opt/zooservices_user/bob",
            "exp": "1714575246",
            "iat": "1714488846",
            "jti": "60d6ecaa-fd29-46a3-b04a-6fdc36e9d549",
            "iss": "https://keycloak.mkube.dec.earthdaily.com/realms/master",
            "aud": "account",
            "sub": "c3c33ca9-97f7-459a-ae34-8cd02380218b",
            "typ": "Bearer",
            "azp": "ws-bob",
            "session_state": "7cb3820c-24e9-4c15-8f40-4c0191c4e804",
            "acr": "1",
            "allowed-origins": "['*']",
            "realm_access": "{'roles': ['default-roles-master', 'offline_access', 'uma_authorization']}",
            "resource_access": "{'account': {'roles': ['manage-account', 'manage-account-links', 'view-profile']}, 'ws-bob': {'roles': ['uma_protection']}}",
            "scope": "profile email",
            "sid": "7cb3820c-24e9-4c15-8f40-4c0191c4e804",
            "email_verified": "False",
            "preferred_username": "bob",
            "jwt": "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJaYnM2bTlXdndRWHZ2akxKTF9BRTlXUERsQVV4TkY4YXBGVFpmU3JRb2FZIn0.eyJleHAiOjE3MTQ1NzUyNDYsImlhdCI6MTcxNDQ4ODg0NiwianRpIjoiNjBkNmVjYWEtZmQyOS00NmEzLWIwNGEtNmZkYzM2ZTlkNTQ5IiwiaXNzIjoiaHR0cHM6Ly9rZXljbG9hay5ta3ViZS5kZWMuZWFydGhkYWlseS5jb20vcmVhbG1zL21hc3RlciIsImF1ZCI6ImFjY291bnQiLCJzdWIiOiJjM2MzM2NhOS05N2Y3LTQ1OWEtYWUzNC04Y2QwMjM4MDIxOGIiLCJ0eXAiOiJCZWFyZXIiLCJhenAiOiJ3cy1ib2IiLCJzZXNzaW9uX3N0YXRlIjoiN2NiMzgyMGMtMjRlOS00YzE1LThmNDAtNGMwMTkxYzRlODA0IiwiYWNyIjoiMSIsImFsbG93ZWQtb3JpZ2lucyI6WyIqIl0sInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJkZWZhdWx0LXJvbGVzLW1hc3RlciIsIm9mZmxpbmVfYWNjZXNzIiwidW1hX2F1dGhvcml6YXRpb24iXX0sInJlc291cmNlX2FjY2VzcyI6eyJhY2NvdW50Ijp7InJvbGVzIjpbIm1hbmFnZS1hY2NvdW50IiwibWFuYWdlLWFjY291bnQtbGlua3MiLCJ2aWV3LXByb2ZpbGUiXX0sIndzLWJvYiI6eyJyb2xlcyI6WyJ1bWFfcHJvdGVjdGlvbiJdfX0sInNjb3BlIjoicHJvZmlsZSBlbWFpbCIsInNpZCI6IjdjYjM4MjBjLTI0ZTktNGMxNS04ZjQwLTRjMDE5MWM0ZTgwNCIsImVtYWlsX3ZlcmlmaWVkIjpmYWxzZSwicHJlZmVycmVkX3VzZXJuYW1lIjoiYm9iIn0.HBAoVVTuR9K5iYp__zg89981lI7X_8HhdzdJEL_UrRDMbNarV3-b373pw3SCtvZHDBPtavJhXDqKFnYsczGr8sgXshQGze_uKMjdfVqAp4e7_eqbjpIjC8b1-1LRLAoARFidUhUkpI5pyySIacXgG-F6AuGuLVxCi7nPoBI4dMbz-UJm4URm0iNuYcRcKuLInMbrteWvlq1sB2g4eZMsrldoy-r2K1dHARQ5Y34gCttT4Rw0YeXG9ZPTuGj9ipB2H5eAdSmJ4BRqBAmCLbo7oek7dUpvrtj5K4ZSFikDWVMRQfhICZ_KdzTI5ASd19QW-y4qF8SZOt0p9qhnE1diKA"
        },
        "request": {
            "jrequest": "cwlVersion: v1.0\n$namespaces:\n  s: https://schema.org/\ns:softwareVersion: 1.4.1\nschemas:\n  - http://schema.org/version/9.0/schemaorg-current-http.rdf\n$graph:\n  - class: Workflow\n    id: custom5\n    label: Water bodies detection based on NDWI and otsu threshold\n    doc: Water bodies detection based on NDWI and otsu threshold\n    requirements:\n      - class: ScatterFeatureRequirement\n      - class: SubworkflowFeatureRequirement\n    inputs:\n      aoi:\n        label: area of interest\n        doc: area of interest as a bounding box\n        type: string\n      epsg:\n        label: EPSG code\n        doc: EPSG code\n        type: string\n        default: EPSG:4326\n      stac_items:\n        label: Sentinel-2 STAC items\n        doc: list of Sentinel-2 COG STAC items\n        type: string[]\n      bands:\n        label: bands used for the NDWI\n        doc: bands used for the NDWI\n        type: string[]\n        default:\n          - green\n          - nir\n    outputs:\n      - id: stac\n        outputSource:\n          - node_stac/stac_catalog\n        type: Directory\n    steps:\n      node_water_bodies:\n        run: '#detect_water_body'\n        in:\n          item: stac_items\n          aoi: aoi\n          epsg: epsg\n          bands: bands\n        out:\n          - detected_water_body\n        scatter: item\n        scatterMethod: dotproduct\n      node_stac:\n        run: '#stac'\n        in:\n          item: stac_items\n          rasters:\n            source: node_water_bodies/detected_water_body\n        out:\n          - stac_catalog\n  - class: Workflow\n    id: detect_water_body\n    label: Water body detection based on NDWI and otsu threshold\n    doc: Water body detection based on NDWI and otsu threshold\n    requirements:\n      - class: ScatterFeatureRequirement\n    inputs:\n      aoi:\n        doc: area of interest as a bounding box\n        type: string\n      epsg:\n        doc: EPSG code\n        type: string\n        default: EPSG:4326\n      bands:\n        doc: bands used for the NDWI\n        type: string[]\n      item:\n        doc: STAC item\n        type: string\n    outputs:\n      - id: detected_water_body\n        outputSource:\n          - node_otsu/binary_mask_item\n        type: File\n    steps:\n      node_crop:\n        run: '#crop'\n        in:\n          item: item\n          aoi: aoi\n          epsg: epsg\n          band: bands\n        out:\n          - cropped\n        scatter: band\n        scatterMethod: dotproduct\n      node_normalized_difference:\n        run: '#norm_diff'\n        in:\n          rasters:\n            source: node_crop/cropped\n        out:\n          - ndwi\n      node_otsu:\n        run: '#otsu'\n        in:\n          raster:\n            source: node_normalized_difference/ndwi\n        out:\n          - binary_mask_item\n  - class: CommandLineTool\n    id: crop\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/crop:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      item:\n        type: string\n        inputBinding:\n          prefix: '--input-item'\n      aoi:\n        type: string\n        inputBinding:\n          prefix: '--aoi'\n      epsg:\n        type: string\n        inputBinding:\n          prefix: '--epsg'\n      band:\n        type: string\n        inputBinding:\n          prefix: '--band'\n    outputs:\n      cropped:\n        outputBinding:\n          glob: '*.tif'\n        type: File\n  - class: CommandLineTool\n    id: norm_diff\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/norm_diff:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      rasters:\n        type: File[]\n        inputBinding:\n          position: 1\n    outputs:\n      ndwi:\n        outputBinding:\n          glob: '*.tif'\n        type: File\n  - class: CommandLineTool\n    id: otsu\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/otsu:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      raster:\n        type: File\n        inputBinding:\n          position: 1\n    outputs:\n      binary_mask_item:\n        outputBinding:\n          glob: '*.tif'\n        type: File\n  - class: CommandLineTool\n    id: stac\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/stac:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      item:\n        type:\n          type: array\n          items: string\n          inputBinding:\n            prefix: '--input-item'\n      rasters:\n        type:\n          type: array\n          items: File\n          inputBinding:\n            prefix: '--water-body'\n    outputs:\n      stac_catalog:\n        outputBinding:\n          glob: .\n        type: Directory",
            "w": "custom5",
            "Identifier": "DeployProcess",
            "response": "raw",
            "metapath": ""
        },
        "renv": {
            "SHELL": "/bin/bash",
            "ZOO_PROJECT_DRU_POSTGRESQL_SERVICE_PORT": "5432",
            "KUBERNETES_SERVICE_PORT_HTTPS": "443",
            "ZOO_PROJECT_DRU_PROTECTION_PORT_3000_TCP_PROTO": "tcp",
            "ZOO_PROJECT_DRU_KUBEPROXY_SERVICE_PORT": "8001",
            "WRAPPER_MAIN": "/assets/main.yaml",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_15672_TCP": "tcp://10.108.219.38:15672",
            "KUBERNETES_SERVICE_PORT": "443",
            "ZOO_PROJECT_DRU_SERVICE_SERVICE_PORT": "80",
            "ZOO_PROJECT_DRU_KUBEPROXY_PORT_8001_TCP": "tcp://10.101.16.188:8001",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_15672_TCP_PROTO": "tcp",
            "ZOO_PROJECT_DRU_PROTECTION_SERVICE_PORT": "3000",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_5672_TCP_PORT": "5672",
            "HOSTNAME": "zoo-project-dru-zoofpm-5dccdbf87f-jqrk8",
            "ZOO_PROJECT_DRU_SERVICE_PORT_80_TCP": "tcp://10.110.200.42:80",
            "ZOO_PROJECT_DRU_PROTECTION_PORT_4000_TCP_PROTO": "tcp",
            "PGPORT": "5432",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_4369_TCP_PORT": "4369",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_15672_TCP_ADDR": "10.108.219.38",
            "PGPASSWORD": "zoo",
            "ZOO_PROJECT_DRU_PROTECTION_SERVICE_PORT_ADMIN": "4000",
            "ZOO_PROJECT_DRU_SERVICE_PORT_80_TCP_PORT": "80",
            "ZOO_RABBITMQ_HOST": "zoo-project-dru-rabbitmq",
            "STAGEIN_AWS_SERVICEURL": "http://data.cloudferro.com",
            "DEFAULT_MAX_RAM": "1024",
            "WRAPPER_RULES": "/assets/rules.yaml",
            "ZOO_PROJECT_DRU_KUBEPROXY_SERVICE_PORT_HTTP_KUBEPROXY": "8001",
            "ZOO_PROJECT_DRU_POSTGRESQL_PORT": "tcp://10.99.8.177:5432",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_5672_TCP": "tcp://10.108.219.38:5672",
            "CALRISSIAN_IMAGE": "terradue/calrissian:0.12.0",
            "PWD": "/usr/lib/cgi-bin",
            "STAGEIN_AWS_ACCESS_KEY_ID": "test",
            "LOGNAME": "www-data",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_5672_TCP_PROTO": "tcp",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_5672_TCP_ADDR": "10.108.219.38",
            "ZOO_PROJECT_DRU_POSTGRESQL_PORT_5432_TCP_PORT": "5432",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_15672_TCP_PORT": "15672",
            "ZOO_PROJECT_DRU_PROTECTION_PORT": "tcp://10.103.238.50:3000",
            "ZOO_PROJECT_DRU_RABBITMQ_SERVICE_PORT": "5672",
            "ZOO_PROJECT_DRU_PROTECTION_PORT_4000_TCP_PORT": "4000",
            "ZOO_PROJECT_DRU_PROTECTION_PORT_3000_TCP_PORT": "3000",
            "_": "./zoo_loader_fpm",
            "DEFAULT_VOLUME_SIZE": "10190",
            "ZOO_PROJECT_DRU_RABBITMQ_SERVICE_PORT_EPMD": "4369",
            "ZOO_PROJECT_DRU_KUBEPROXY_PORT_8001_TCP_PROTO": "tcp",
            "STAGEOUT_OUTPUT": "eoepca",
            "ZOO_PROJECT_DRU_KUBEPROXY_PORT": "tcp://10.101.16.188:8001",
            "HOME": "/var/www",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_25672_TCP_ADDR": "10.108.219.38",
            "KUBERNETES_PORT_443_TCP": "tcp://10.96.0.1:443",
            "ZOO_PROJECT_DRU_KUBEPROXY_PORT_8001_TCP_PORT": "8001",
            "STAGEOUT_AWS_ACCESS_KEY_ID": "eoepca",
            "ZOO_PROJECT_DRU_POSTGRESQL_PORT_5432_TCP_ADDR": "10.99.8.177",
            "STAGEOUT_AWS_REGION": "RegionOne",
            "ZOO_PROJECT_DRU_SERVICE_PORT_80_TCP_PROTO": "tcp",
            "PGUSER": "zoo",
            "ZOO_PROJECT_DRU_SERVICE_SERVICE_PORT_HTTP": "80",
            "DEFAULT_MAX_CORES": "2",
            "ZOO_PROJECT_DRU_PROTECTION_SERVICE_HOST": "10.103.238.50",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_4369_TCP_ADDR": "10.108.219.38",
            "ZOO_PROJECT_DRU_RABBITMQ_SERVICE_PORT_DIST": "25672",
            "ZOO_PROJECT_DRU_SERVICE_PORT": "tcp://10.110.200.42:80",
            "ZOO_PROJECT_DRU_PROTECTION_PORT_4000_TCP": "tcp://10.103.238.50:4000",
            "STAGEOUT_AWS_SECRET_ACCESS_KEY": "changeme",
            "ZOO_PROJECT_DRU_PROTECTION_PORT_4000_TCP_ADDR": "10.103.238.50",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_25672_TCP": "tcp://10.108.219.38:25672",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT": "tcp://10.108.219.38:5672",
            "USER": "www-data",
            "ZOO_PROJECT_DRU_RABBITMQ_SERVICE_HOST": "10.108.219.38",
            "ZOO_PROJECT_DRU_SERVICE_PORT_80_TCP_ADDR": "10.110.200.42",
            "ZOO_PROJECT_DRU_POSTGRESQL_PORT_5432_TCP_PROTO": "tcp",
            "ZOO_PROJECT_DRU_RABBITMQ_SERVICE_PORT_AMQP": "5672",
            "STAGEIN_AWS_REGION": "RegionOne",
            "SHLVL": "2",
            "STAGEOUT_AWS_SERVICEURL": "https://minio.mkube.dec.earthdaily.com",
            "HTTP_PROXY": "http://zoo-project-dru-kubeproxy.zoo.svc.cluster.local:8001",
            "KUBERNETES_PORT_443_TCP_PROTO": "tcp",
            "PGDATABASE": "zoo",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_25672_TCP_PORT": "25672",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_25672_TCP_PROTO": "tcp",
            "ZOO_PROJECT_DRU_POSTGRESQL_SERVICE_PORT_TCP_POSTGRESQL": "5432",
            "KUBERNETES_PORT_443_TCP_ADDR": "10.96.0.1",
            "ZOO_PROJECT_DRU_PROTECTION_PORT_3000_TCP": "tcp://10.103.238.50:3000",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_4369_TCP_PROTO": "tcp",
            "ZOO_PROJECT_DRU_RABBITMQ_SERVICE_PORT_HTTP_STATS": "15672",
            "PGHOST": "zoo-project-dru-postgresql-hl",
            "ZOO_PROJECT_DRU_RABBITMQ_PORT_4369_TCP": "tcp://10.108.219.38:4369",
            "WRAPPER_STAGE_OUT": "/assets/stageout.yaml",
            "KUBERNETES_SERVICE_HOST": "10.96.0.1",
            "ZOO_PROJECT_DRU_KUBEPROXY_PORT_8001_TCP_ADDR": "10.101.16.188",
            "ZOO_PROJECT_DRU_PROTECTION_SERVICE_PORT_PROXY": "3000",
            "KUBERNETES_PORT": "tcp://10.96.0.1:443",
            "KUBERNETES_PORT_443_TCP_PORT": "443",
            "ZOO_PROJECT_DRU_POSTGRESQL_SERVICE_HOST": "10.99.8.177",
            "ZOO_PROJECT_DRU_POSTGRESQL_PORT_5432_TCP": "tcp://10.99.8.177:5432",
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin",
            "ZOO_PROJECT_DRU_SERVICE_SERVICE_HOST": "10.110.200.42",
            "ZOO_PROJECT_DRU_PROTECTION_PORT_3000_TCP_ADDR": "10.103.238.50",
            "WRAPPER_STAGE_IN": "/assets/stagein.yaml",
            "MAIL": "/var/mail/www-data",
            "STORAGE_CLASS": "standard",
            "DEBIAN_FRONTEND": "noninteractive",
            "ZOO_PROJECT_DRU_KUBEPROXY_SERVICE_HOST": "10.101.16.188",
            "STAGEIN_AWS_SECRET_ACCESS_KEY": "test",
            "OLDPWD": "/opt/ZOO-Project",
            "PYTHONPATH": "/usr/miniconda3/envs/ades-dev/lib/python3.8/site-packages",
            "CONTEXT_DOCUMENT_ROOT": "/usr/lib/cgi-bin/",
            "SERVICES_NAMESPACE": "bob",
            "jrequest": "cwlVersion: v1.0\n$namespaces:\n  s: https://schema.org/\ns:softwareVersion: 1.4.1\nschemas:\n  - http://schema.org/version/9.0/schemaorg-current-http.rdf\n$graph:\n  - class: Workflow\n    id: custom5\n    label: Water bodies detection based on NDWI and otsu threshold\n    doc: Water bodies detection based on NDWI and otsu threshold\n    requirements:\n      - class: ScatterFeatureRequirement\n      - class: SubworkflowFeatureRequirement\n    inputs:\n      aoi:\n        label: area of interest\n        doc: area of interest as a bounding box\n        type: string\n      epsg:\n        label: EPSG code\n        doc: EPSG code\n        type: string\n        default: EPSG:4326\n      stac_items:\n        label: Sentinel-2 STAC items\n        doc: list of Sentinel-2 COG STAC items\n        type: string[]\n      bands:\n        label: bands used for the NDWI\n        doc: bands used for the NDWI\n        type: string[]\n        default:\n          - green\n          - nir\n    outputs:\n      - id: stac\n        outputSource:\n          - node_stac/stac_catalog\n        type: Directory\n    steps:\n      node_water_bodies:\n        run: '#detect_water_body'\n        in:\n          item: stac_items\n          aoi: aoi\n          epsg: epsg\n          bands: bands\n        out:\n          - detected_water_body\n        scatter: item\n        scatterMethod: dotproduct\n      node_stac:\n        run: '#stac'\n        in:\n          item: stac_items\n          rasters:\n            source: node_water_bodies/detected_water_body\n        out:\n          - stac_catalog\n  - class: Workflow\n    id: detect_water_body\n    label: Water body detection based on NDWI and otsu threshold\n    doc: Water body detection based on NDWI and otsu threshold\n    requirements:\n      - class: ScatterFeatureRequirement\n    inputs:\n      aoi:\n        doc: area of interest as a bounding box\n        type: string\n      epsg:\n        doc: EPSG code\n        type: string\n        default: EPSG:4326\n      bands:\n        doc: bands used for the NDWI\n        type: string[]\n      item:\n        doc: STAC item\n        type: string\n    outputs:\n      - id: detected_water_body\n        outputSource:\n          - node_otsu/binary_mask_item\n        type: File\n    steps:\n      node_crop:\n        run: '#crop'\n        in:\n          item: item\n          aoi: aoi\n          epsg: epsg\n          band: bands\n        out:\n          - cropped\n        scatter: band\n        scatterMethod: dotproduct\n      node_normalized_difference:\n        run: '#norm_diff'\n        in:\n          rasters:\n            source: node_crop/cropped\n        out:\n          - ndwi\n      node_otsu:\n        run: '#otsu'\n        in:\n          raster:\n            source: node_normalized_difference/ndwi\n        out:\n          - binary_mask_item\n  - class: CommandLineTool\n    id: crop\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/crop:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      item:\n        type: string\n        inputBinding:\n          prefix: '--input-item'\n      aoi:\n        type: string\n        inputBinding:\n          prefix: '--aoi'\n      epsg:\n        type: string\n        inputBinding:\n          prefix: '--epsg'\n      band:\n        type: string\n        inputBinding:\n          prefix: '--band'\n    outputs:\n      cropped:\n        outputBinding:\n          glob: '*.tif'\n        type: File\n  - class: CommandLineTool\n    id: norm_diff\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/norm_diff:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      rasters:\n        type: File[]\n        inputBinding:\n          position: 1\n    outputs:\n      ndwi:\n        outputBinding:\n          glob: '*.tif'\n        type: File\n  - class: CommandLineTool\n    id: otsu\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/otsu:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      raster:\n        type: File\n        inputBinding:\n          position: 1\n    outputs:\n      binary_mask_item:\n        outputBinding:\n          glob: '*.tif'\n        type: File\n  - class: CommandLineTool\n    id: stac\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/stac:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      item:\n        type:\n          type: array\n          items: string\n          inputBinding:\n            prefix: '--input-item'\n      rasters:\n        type:\n          type: array\n          items: File\n          inputBinding:\n            prefix: '--water-body'\n    outputs:\n      stac_catalog:\n        outputBinding:\n          glob: .\n        type: Directory"
        },
        "additional_parameters": {
            "APP": "zoo-project-dru",
            "STAGEIN_AWS_REGION": "RegionOne",
            "STAGEIN_AWS_ACCESS_KEY_ID": "minio-admin",
            "STAGEIN_AWS_SECRET_ACCESS_KEY": "minio-secret-password",
            "STAGEIN_AWS_SERVICEURL": "http://s3-service.zoo.svc.cluster.local:9000",
            "STAGEOUT_AWS_REGION": "RegionOne",
            "STAGEOUT_AWS_ACCESS_KEY_ID": "minio-admin",
            "STAGEOUT_AWS_SECRET_ACCESS_KEY": "minio-secret-password",
            "STAGEOUT_AWS_SERVICEURL": "http://s3-service.zoo.svc.cluster.local:9000",
            "STAGEOUT_OUTPUT": "s3://processingresults"
        },
        "pod_env_vars": {
            "A": "1",
            "B": "2"
        },
        "sqlenv": {
            "lastQuery": "select id,identifier,title,abstract,version,service_type,service_provider,conf_id,mutable,user_id from ows_process WHERE identifier='DeployProcess' AND (user_id=0 or user_id=(SELECT id FROM public.users WHERE name='bob'))",
            "length": "2",
            "isArray": "true",
            "lastResult": "Failed",
            "lastQuery_1": "select id,identifier,title,abstract,version,service_type,service_provider,conf_id,mutable,user_id from ows_process WHERE identifier='DeployProcess' AND (user_id=0 or user_id=(SELECT id FROM public.users WHERE name='bob'))",
            "lastResult_1": "Failed"
        }
    }
    inputs = {
        "applicationPackage": {
            "value": [
                "cwlVersion: v1.0\n$namespaces:\n  s: https://schema.org/\ns:softwareVersion: 1.4.1\nschemas:\n  - http://schema.org/version/9.0/schemaorg-current-http.rdf\n$graph:\n  - class: Workflow\n    id: custom5\n    label: Water bodies detection based on NDWI and otsu threshold\n    doc: Water bodies detection based on NDWI and otsu threshold\n    requirements:\n      - class: ScatterFeatureRequirement\n      - class: SubworkflowFeatureRequirement\n    inputs:\n      aoi:\n        label: area of interest\n        doc: area of interest as a bounding box\n        type: string\n      epsg:\n        label: EPSG code\n        doc: EPSG code\n        type: string\n        default: EPSG:4326\n      stac_items:\n        label: Sentinel-2 STAC items\n        doc: list of Sentinel-2 COG STAC items\n        type: string[]\n      bands:\n        label: bands used for the NDWI\n        doc: bands used for the NDWI\n        type: string[]\n        default:\n          - green\n          - nir\n    outputs:\n      - id: stac\n        outputSource:\n          - node_stac/stac_catalog\n        type: Directory\n    steps:\n      node_water_bodies:\n        run: '#detect_water_body'\n        in:\n          item: stac_items\n          aoi: aoi\n          epsg: epsg\n          bands: bands\n        out:\n          - detected_water_body\n        scatter: item\n        scatterMethod: dotproduct\n      node_stac:\n        run: '#stac'\n        in:\n          item: stac_items\n          rasters:\n            source: node_water_bodies/detected_water_body\n        out:\n          - stac_catalog\n  - class: Workflow\n    id: detect_water_body\n    label: Water body detection based on NDWI and otsu threshold\n    doc: Water body detection based on NDWI and otsu threshold\n    requirements:\n      - class: ScatterFeatureRequirement\n    inputs:\n      aoi:\n        doc: area of interest as a bounding box\n        type: string\n      epsg:\n        doc: EPSG code\n        type: string\n        default: EPSG:4326\n      bands:\n        doc: bands used for the NDWI\n        type: string[]\n      item:\n        doc: STAC item\n        type: string\n    outputs:\n      - id: detected_water_body\n        outputSource:\n          - node_otsu/binary_mask_item\n        type: File\n    steps:\n      node_crop:\n        run: '#crop'\n        in:\n          item: item\n          aoi: aoi\n          epsg: epsg\n          band: bands\n        out:\n          - cropped\n        scatter: band\n        scatterMethod: dotproduct\n      node_normalized_difference:\n        run: '#norm_diff'\n        in:\n          rasters:\n            source: node_crop/cropped\n        out:\n          - ndwi\n      node_otsu:\n        run: '#otsu'\n        in:\n          raster:\n            source: node_normalized_difference/ndwi\n        out:\n          - binary_mask_item\n  - class: CommandLineTool\n    id: crop\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/crop:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      item:\n        type: string\n        inputBinding:\n          prefix: '--input-item'\n      aoi:\n        type: string\n        inputBinding:\n          prefix: '--aoi'\n      epsg:\n        type: string\n        inputBinding:\n          prefix: '--epsg'\n      band:\n        type: string\n        inputBinding:\n          prefix: '--band'\n    outputs:\n      cropped:\n        outputBinding:\n          glob: '*.tif'\n        type: File\n  - class: CommandLineTool\n    id: norm_diff\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/norm_diff:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      rasters:\n        type: File[]\n        inputBinding:\n          position: 1\n    outputs:\n      ndwi:\n        outputBinding:\n          glob: '*.tif'\n        type: File\n  - class: CommandLineTool\n    id: otsu\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/otsu:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      raster:\n        type: File\n        inputBinding:\n          position: 1\n    outputs:\n      binary_mask_item:\n        outputBinding:\n          glob: '*.tif'\n        type: File\n  - class: CommandLineTool\n    id: stac\n    requirements:\n      InlineJavascriptRequirement: {}\n      EnvVarRequirement:\n        envDef:\n          PATH: /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n          PYTHONPATH: /app\n      ResourceRequirement:\n        coresMax: 1\n        ramMax: 512\n    hints:\n      DockerRequirement:\n        dockerPull: ghcr.io/terradue/ogc-eo-application-package-hands-on/stac:1.5.0\n    baseCommand:\n      - python\n      - '-m'\n      - app\n    arguments: []\n    inputs:\n      item:\n        type:\n          type: array\n          items: string\n          inputBinding:\n            prefix: '--input-item'\n      rasters:\n        type:\n          type: array\n          items: File\n          inputBinding:\n            prefix: '--water-body'\n    outputs:\n      stac_catalog:\n        outputBinding:\n          glob: .\n        type: Directory"
            ],
            "mimeType": [
                "application/cwl"
            ],
            "cache_file": [
                "/tmp/zTmp/Input_applicationPackage_7e65e196-0701-11ef-8b69-0242ac110035_0.txt"
            ],
            "length": "1",
            "isArray": "true",
            "mediaType": "application/cwl",
            "inRequest": "true",
            "minOccurs": "1",
            "maxOccurs": "1",
            "cache_url": "https://zoo.mkube.dec.earthdaily.com/temp//Input_applicationPackage_7e65e196-0701-11ef-8b69-0242ac110035_0.txt",
            "byValue": "true"
        }
    }
    outputs = {
        "Result": {
            "MimeType": "application/json",
            "inRequest": "false"
        }
    }
    DeployProcess(conf, inputs, outputs)