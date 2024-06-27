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

import sys
import json
import os
import shutil
from pathlib import Path
from collections import namedtuple

import zoo
import yaml
from cookiecutter.main import cookiecutter


class Process:
    def __init__(
        self,
        identifier,
        version,
        title=None,
        description=None,
        store_supported=True,
        status_supported=True,
        service_type=None,
        service_provider=None,
    ):
        self.identifier = identifier
        self.version = version
        self.title = title or identifier
        if self.title:
            self.title = str(self.title)
        self.description = description or title
        if self.description:
            self.description = str(self.description)
        self.store_supported = store_supported
        self.status_supported = status_supported
        self.service_type = service_type
        self.service_provider = service_provider
        self.version = version
        self.inputs = []
        self.outputs = []

    def __repr__(self):
        return f"Process(\n\tidentifier={self.identifier}, \n\tversion={self.version}, \n\ttitle={self.title}, \n\tdescription={self.description}, \n\tstore_supported={self.store_supported}, \n\tstatus_supported={self.status_supported}, \n\tservice_type={self.service_type}, \n\tservice_provider={self.service_provider}, \n\tversion={self.version}, \n\tinputs={self.inputs}, \n\toutputs={self.outputs})"

    @classmethod
    def create_from_cwl(cls, cwl, workflow_id=None, workflow_parameters=[]):
        """
        Creates a Process object from a dictionary representing the CWL YAML file.
        """
        print(f"cwl = {cwl}", file=sys.stderr)

        ################################################################
        workflow_id = workflow_id or cwl.get("metadata", {}).get("name", "unknown")
        version = cwl.get("metadata", {}).get("version", "unknown")
        title = cwl.get("metadata", {}).get("title", "unknown")
        description = cwl.get("metadata", {}).get("description", "unknown")
        process = Process(
            identifier=workflow_id,
            version=version,
            title=title,
            description=description,
        )
        ################################################################

        print(f"process before = {process}", file=sys.stderr)

        print("adding inputs", file=sys.stderr)
        # process.add_inputs_from_cwl(workflow.inputs, len(workflow.id)) #commenting this out will avoid validating in input and still we have the service properly deployed

        print(f"workflow_parameters = {workflow_parameters}", file=sys.stderr)
        for workflow_parameter in workflow_parameters:
            process_input = ProcessInput(
                identifier=workflow_parameter.get("name", "unknown"),
                title=workflow_parameter.get("title", "unknown"),
                description=workflow_parameter.get("description", "unknown"),
                input_type=workflow_parameter.get("input_type", "string"),
            )

            process_input.min_occurs = 1
            if process_input.type == "list":
                process_input.max_occurs = 0
            else:
                process_input.max_occurs = 1

            process_input.default_value = None
            process_input.possible_values = None
            process_input.is_complex = False
            process_input.is_file = False
            process_input.file_content_type = None
            process_input.is_directory = False

            process.inputs.append(process_input)

        print(f"inputs = {process.inputs}", file=sys.stderr)
        print("adding outputs", file=sys.stderr)
        # process.add_outputs_from_cwl(workflow.outputs, len(workflow.id))
        out1 = ProcessOutput(
            identifier="stac",
            title="STAC",
            description="STAC item",
            input_type="string",
        )
        out1.min_occurs = 1
        out1.max_occurs = 1
        out1.is_complex = True
        process.outputs = [out1]

        print(f"outputs = {process.outputs}", file=sys.stderr)

        print(f"process after = {process}", file=sys.stderr)

        return process

    def add_inputs_from_cwl(self, inputs, trim_len):
        """
        Adds a process input from a CWL input representation.
        """
        print(f"add_inputs_from_cwl. trim_len = {trim_len}", file=sys.stderr)

        for i, input in enumerate(inputs):
            print(f"input {i} = {input}", file=sys.stderr)
            process_input = ProcessInput.create_from_cwl(input, trim_len)
            self.inputs.append(process_input)

    def add_outputs_from_cwl(self, outputs, trim_len):
        """
        Adds a process output from a CWL input representation.
        """
        print(f"add_outputs_from_cwl. trim_len = {trim_len}", file=sys.stderr)
        for i, output in enumerate(outputs):
            print(f"output {i} = {output}", file=sys.stderr)
            process_output = ProcessOutput.create_from_cwl(output, trim_len)
            self.outputs.append(process_output)

    def write_zcfg(self, stream):
        """
        Writes the configuration file for the Zoo process (.zfcg) to a stream.
        """

        print("[{0}]".format(self.identifier), file=stream)
        if self.title:
            print("  Title = {0}".format(self.title), file=stream)
        if self.description:
            print("  Abstract = {0}".format(self.description), file=stream)
        if self.service_provider:
            print("  serviceType = {0}".format(self.service_type), file=stream)
            print("  serviceProvider = {0}".format(self.service_provider), file=stream)
        if self.version:
            print("  processVersion = {0}".format(self.version), file=stream)
        print(
            "  storeSupported = {0}".format(
                "true" if self.store_supported else "false"
            ),
            file=stream,
        )
        print(
            "  statusSupported = {0}".format(
                "true" if self.status_supported else "false"
            ),
            file=stream,
        )

        print("  <DataInputs>", file=stream)
        for input in self.inputs:
            print("    [{0}]".format(input.identifier), file=stream)
            print("      Title = {0}".format(input.title), file=stream)
            print("      Abstract = {0}".format(input.description), file=stream)
            print("      minOccurs = {0}".format(input.min_occurs), file=stream)
            print(
                "      maxOccurs = {0}".format(
                    999 if input.max_occurs == 0 else input.max_occurs
                ),
                file=stream,
            )
            if input.is_complex:
                pass
            else:
                print("      <LiteralData>", file=stream)
                print("        dataType = {0}".format(input.type), file=stream)
                if input.possible_values:
                    print(
                        "        AllowedValues = {0}".format(
                            ",".join(input.possible_values)
                        ),
                        file=stream,
                    )
                if input.default_value:
                    print("        <Default>", file=stream)
                    print(
                        "          value = {0}".format(input.default_value), file=stream
                    )
                    print("        </Default>", file=stream)
                else:
                    print("        <Default/>", file=stream)
                print("      </LiteralData>", file=stream)
        print("  </DataInputs>", file=stream)

        print("  <DataOutputs>", file=stream)
        for output in self.outputs:
            print("    [{0}]".format(output.identifier), file=stream)
            print("      Title = {0}".format(output.title), file=stream)
            print("      Abstract = {0}".format(output.description), file=stream)
            if output.is_complex:
                print("      <ComplexData>", file=stream)
                print("        <Default>", file=stream)
                print(
                    "          mimeType = {0}".format(
                        output.file_content_type
                        if output.file_content_type
                        else "text/plain"
                    ),
                    file=stream,
                )
                print("        </Default>", file=stream)
                print("      </ComplexData>", file=stream)
            else:
                print("      <LiteralData>", file=stream)
                print("        dataType = {0}".format(input.type), file=stream)
                print("        <Default/>", file=stream)
                print("      </LiteralData>", file=stream)
        print("  </DataOutputs>", file=stream)

    def run_sql(self, conf):
        """
        Store the metadata informations in the ZOO-Project database
        """
        import psycopg2
        import psycopg2.extensions

        psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)

        # to check if the user is anonymous: use conf["lenv"]["cwd"]
        # if conf["lenv"]["cwd"] == "/usr/lib/cgi-bin" -> anonymous
        # else -> conf["auth_env"]["user"]
        if conf["lenv"]["cwd"] == "/usr/lib/cgi-bin":
            self.user = "anonymous"
        else:
            self.user = conf["auth_env"]["user"]

        # original code
        # if "auth_env" in conf:
        #     self.user = conf["auth_env"]["user"]
        # else:
        #     self.user = "anonymous"

        print(f"[run_sql] user = {self.user}", file=sys.stderr)

        conn = psycopg2.connect(
            "host=%s port=%s dbname=%s user=%s password=%s"
            % (
                conf["metadb"]["host"],
                conf["metadb"]["port"],
                conf["metadb"]["dbname"],
                conf["metadb"]["user"],
                conf["metadb"]["password"],
            )
        )
        cur = conn.cursor()

        if "orequest_method" in conf["lenv"]:
            print(
                f"Delete from DB(collectiondb.ows_process) process {self.identifier} for user {self.user}",
                file=sys.stderr,
            )
            cur.execute(
                "DELETE FROM collectiondb.ows_process WHERE identifier=$q$%s$q$ and user_id=(select id from public.users where name=$q$%s$q$)"
                % (self.identifier, self.user)
            )
        conn.commit()

        print(
            f"Select from DB(collectiondb.ows_process) process {self.identifier} for user {self.user}",
            file=sys.stderr,
        )
        cur.execute(
            "SELECT id FROM collectiondb.ows_process WHERE identifier=$q$%s$q$ and user_id=(select id from public.users where name=$q$%s$q$)"
            % (self.identifier, self.user)
        )

        vals = cur.fetchone()
        if vals is not None:
            print(
                f"ows_process {self.identifier} for user {self.user} already exists in DB. Returning False",
                file=sys.stderr,
            )
            conn.close()
            return False

        # not sure why we need to commit here
        conn.commit()

        print(
            f"Inserting CollectionDB.zoo_DeploymentMetadata executable_name {self.service_provider} with type {self.service_type} into DB",
            file=sys.stderr,
        )
        cur.execute(
            (
                "INSERT INTO CollectionDB.zoo_DeploymentMetadata"
                + "(executable_name,service_type_id)"
                + " VALUES "
                + " ($q${0}$q$,"
                + "(SELECT id from CollectionDB.zoo_ServiceTypes WHERE service_type=$q${1}$q$));"
            ).format(self.service_provider, self.service_type)
        )

        print(
            "Inserting into CollectionDB.zoo_PrivateMetadata into DB", file=sys.stderr
        )
        cur.execute(
            "INSERT INTO CollectionDB.zoo_PrivateMetadata(id) VALUES (default);"
        )

        print(
            "Inserting into CollectionDB.zoo_DeploymentMetadataAssignment into DB",
            file=sys.stderr,
        )
        cur.execute(
            "INSERT INTO CollectionDB.PrivateMetadataDeploymentMetadataAssignment(private_metadata_id,deployment_metadata_id) VALUES"
            + "((SELECT last_value FROM CollectionDB.zoo_PrivateMetadata_id_seq),"
            + "(SELECT last_value FROM CollectionDB.zoo_DeploymentMetadata_id_seq));"
        )

        try:
            print(
                f"Select user_id from public.users where name={self.user}",
                file=sys.stderr,
            )
            cur.execute(
                "SELECT id from public.users WHERE name = $q${0}$q$".format(self.user)
            )
            if cur.fetchone() is None:
                print(
                    f"User {self.user} not found in public.users. Inserting user into DB",
                    file=sys.stderr,
                )
                cur.execute(
                    "INSERT INTO public.users (name) VALUES ($q${0}$q$)".format(
                        self.user
                    )
                )
        except Exception as e:
            print("Error while inserting user into public.users", file=sys.stderr)
            print(e, file=sys.stderr)
            cur.commit()

        print(
            f"Inserting into CollectionDB.ows_Process identifier={self.identifier}, title={self.title}, abstract={self.description}, version={self.version}, user={self.user} into DB",
            file=sys.stderr,
        )
        cur.execute(
            (
                "INSERT INTO CollectionDB.ows_Process"
                + "(identifier,title,abstract,version,user_id,private_metadata_id,mutable,availability)"
                + "VALUES"
                + "($q${0}$q$,"
                + "$q${1}$q$,"
                + "$q${2}$q$,"
                + "$q${3}$q$,"
                + "(select id from public.users where name=$q${4}$q$),"
                + "(SELECT last_value FROM CollectionDB.PrivateMetadataDeploymentMetadataAssignment_id_seq),"
                + "true,true);"
            ).format(
                self.identifier, self.title, self.description, self.version, self.user
            )
        )

        print("Creating temporary table pid", file=sys.stderr)
        cur.execute(
            "CREATE TEMPORARY TABLE pid AS (select last_value as id from CollectionDB.Descriptions_id_seq);"
        )

        # Inputs treatment
        print("Inserting inputs into DB", file=sys.stderr)
        for input in self.inputs:
            if input.is_complex:
                print("Complex input. Skipping", file=sys.stderr)
                pass
            else:
                print(f"inserting input = {input}", file=sys.stderr)
                print("Inserting into CollectionDB.LiteralDataDomain", file=sys.stderr)
                cur.execute(
                    "INSERT INTO CollectionDB.LiteralDataDomain (def,data_type_id) VALUES "
                    + "(true,(SELECT id from CollectionDB.PrimitiveDatatypes where name = $q${0}$q$));".format(
                        input.type
                    )
                )

                if input.possible_values:
                    print("insert input with possible values", file=sys.stderr)

                    for i in range(len(input.possible_values)):
                        print(
                            f"Inserting into CollectionDB.AllowedValues {input.possible_values[i]}",
                            file=sys.stderr,
                        )
                        cur.execute(
                            "INSERT INTO CollectionDB.AllowedValues (allowed_value) VALUES ($q${0}$q$);".format(
                                input.possible_values[i]
                            )
                        )
                        cur.execute(
                            "INSERT INTO CollectionDB.AllowedValuesAssignment (literal_data_domain_id,allowed_value_id) VALUES ("
                            + "(select last_value as id from CollectionDB.LiteralDataDomain_id_seq)"
                            + "(select last_value as id from CollectionDB.AllowedValues_id_seq)"
                            ");"
                        )

                if input.default_value:
                    print(
                        f"insert input with default value: {input.default_value}",
                        file=sys.stderr,
                    )
                    cur.execute(
                        "UPDATE CollectionDB.LiteralDataDomain"
                        + " set default_value = $q${0}$q$ ".format(input.default_value)
                        + " WHERE id = "
                        + "  ((SELECT last_value FROM CollectionDB.ows_DataDescription_id_seq));"
                    )

            print(
                f"Inserting into CollectionDB.ows_Input identified = {input.identifier}, title = {input.title}, description = {input.description}, min_occurs = {input.min_occurs}, max_occurs = {999 if input.max_occurs == 0 else input.max_occurs}",
                file=sys.stderr,
            )
            cur.execute(
                (
                    "INSERT INTO CollectionDB.ows_Input (identifier,title,abstract,min_occurs,max_occurs) VALUES "
                    + "($q${0}$q$,"
                    + "$q${1}$q$,"
                    + "$q${2}$q$,"
                    + "{3},"
                    + "{4});"
                ).format(
                    input.identifier,
                    input.title,
                    input.description,
                    input.min_occurs,
                    999 if input.max_occurs == 0 else input.max_occurs,
                )
            )
            cur.execute(
                "INSERT INTO CollectionDB.InputDataDescriptionAssignment (input_id,data_description_id) VALUES ((select last_value as id from CollectionDB.Descriptions_id_seq),(select last_value from CollectionDB.ows_DataDescription_id_seq));"
            )
            cur.execute(
                "INSERT INTO CollectionDB.ProcessInputAssignment(process_id,input_id) VALUES((select id from pid),(select last_value as id from CollectionDB.Descriptions_id_seq));"
            )

        # Output treatment
        print("Inserting outputs into DB", file=sys.stderr)
        for output in self.outputs:
            if output.is_complex:
                print("Complex output.", file=sys.stderr)
                cur.execute(
                    "INSERT INTO CollectionDB.ows_Format (def,primitive_format_id) VALUES "
                    + "(true,(SELECT id from CollectionDB.PrimitiveFormats WHERE mime_type='{0}' LIMIT 1));".format(
                        output.file_content_type
                        if output.file_content_type
                        else "text/plain"
                    )
                )

            print(
                f"Inserting into CollectionDB.ows_Output identified = {output.identifier}, title = {output.title}, description = {output.description}",
                file=sys.stderr,
            )
            cur.execute(
                "INSERT INTO CollectionDB.ows_DataDescription (format_id) VALUES ((SELECT last_value FROM CollectionDB.ows_Format_id_seq));"
            )
            cur.execute(
                "INSERT INTO CollectionDB.ows_Output"
                + "(identifier,title,abstract)"
                + " VALUES "
                + "($q${0}$q$,$q${1}$q$,$q${2}$q$);".format(
                    output.identifier, output.title, output.description
                )
            )
            cur.execute(
                "INSERT INTO CollectionDB.OutputDataDescriptionAssignment (output_id,data_description_id) VALUES ((select last_value as id from CollectionDB.Descriptions_id_seq),(select last_value from CollectionDB.ows_DataDescription_id_seq));"
            )
            cur.execute(
                "INSERT INTO CollectionDB.ProcessOutputAssignment(process_id,output_id) VALUES((select id from pid),(select last_value as id from CollectionDB.Descriptions_id_seq));"
            )

        print("Dropping temporary table pid", file=sys.stderr)
        cur.execute("DROP TABLE pid;")

        print("Committing", file=sys.stderr)
        conn.commit()
        conn.close()
        return True

    def write_ogc_api_json(self, stream):
        ogc = self.get_ogc_api_json()
        print(json.dumps(ogc, indent=2), file=stream)

    def write_ogc_api_yaml(self, stream):
        ogc = self.get_ogc_api_json()
        print(yaml.dump(ogc), file=stream)

    def get_ogc_api_json(self):
        ogc = {
            "id": self.identifier,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "jobControlOptions": [],
            "outputTransmission": [],
            "links": [],
            "inputs": {},
            "outputs": {},
        }

        for input in self.inputs:
            ogc_input_schema = {"type": input.type}
            if input.min_occurs == 0:
                ogc_input_schema["nullable"] = True
            elif input.max_occurs != 1:
                ogc_input_schema["minItems"] = input.min_occurs
            if input.max_occurs != 1:
                ogc_input_schema["type"] = "array"
                ogc_input_schema["maxItems"] = (
                    input.max_occurs if input.max_occurs > 1 else 100
                )
                ogc_input_schema["items"] = {"type": input.type}
            if input.possible_values:
                ogc_input_schema["enum"] = input.possible_values.copy()
            if input.default_value:
                ogc_input_schema["default"] = input.default_value
            if input.is_file:
                ogc_input_schema["contentMediaType"] = input.file_content_type()
            elif input.is_directory:
                ogc_input_schema["contentMediaType"] = input.file_content_type()

            ogc_input = {
                "title": input.title,
                "description": input.description,
                "schema": ogc_input_schema,
            }

            if input.is_complex:
                pass  # TODO
            else:
                ogc["inputs"][input.identifier] = ogc_input

        for output in self.outputs:
            ogc_output_schema = {"type": output.type}

            ogc_output = {
                "title": output.title,
                "description": output.description,
                "schema": ogc_output_schema,
            }

            if output.is_complex:
                pass  # TODO
            else:
                ogc["outputs"][output.identifier] = ogc_output
        return ogc


class ProcessInput:
    cwl_type_map = {
        "boolean": "boolean",
        "int": "integer",
        "long": "integer",
        "float": "number",
        "double": "number",
        "string": "string",
        "enum": None,
    }

    def __init__(self, identifier, title=None, description=None, input_type="string"):
        self.identifier = str(identifier)
        self.title = title or identifier
        if self.title:
            self.title = str(self.title)
        self.description = description or title
        if self.description:
            self.description = str(self.description)
        self.type = input_type
        self.min_occurs = 1
        self.max_occurs = 1
        self.default_value = None
        self.possible_values = None
        self.is_complex = False  # TODO
        self.is_file = False
        self.file_content_type = None
        self.is_directory = False

    def __repr__(self):
        return f"ProcessInput(\n\tidentifier={self.identifier}, \n\ttitle={self.title}, \n\tdescription={self.description}, \n\ttype={self.type}, \n\tmin_occurs={self.min_occurs}, \n\tmax_occurs={self.max_occurs}, \n\tdefault_value={self.default_value}, \n\tpossible_values={self.possible_values}, \n\tis_complex={self.is_complex}, \n\tis_file={self.is_file}, \n\tfile_content_type={self.file_content_type}, \n\tis_directory={self.is_directory}\n)"

    @classmethod
    def create_from_cwl(cls, input, trim_len):
        process_input = cls(
            input.id[trim_len + 1 :],
            input.label,
            input.doc,
        )

        process_input.set_type_from_cwl(input, trim_len)

        if input.default:
            process_input.default_value = input.default

        print(f"process_input = {process_input}", file=sys.stderr)

        return process_input

    def set_type_from_cwl(self, input, trim_len):
        # if input.type is something like ['null', 'typename'],
        # it means the input is optional and of type typename
        if isinstance(input.type, str) or (
            isinstance(input.type, list)
            and len(input.type) == 2
            and input.type[0] == "null"
        ):
            type_name = input.type[1] if isinstance(input.type, list) else input.type
            if type_name in self.__class__.cwl_type_map:
                type_name = self.__class__.cwl_type_map[type_name]
            elif type_name == "File":
                type_name = "string"
                self.file_content_type = "text/plain"
            elif type_name == "Directory":
                type_name = "string"
                self.file_content_type = "text/plain"
            else:
                raise Exception(
                    "Unsupported type for input '{0}': {1}".format(input.id, type_name)
                )

            self.type = type_name
            self.min_occurs = 0 if isinstance(input.type, list) else 1
            self.max_occurs = 1
            # 0 means unbounded, TODO: what should be the maxOcccurs value if unbounded is not available?

        # elif isinstance(input.type, cwl_v1_0.InputArraySchema):
        #     type_name = input.type.items

        #     if type_name in self.__class__.cwl_type_map:
        #         type_name = self.__class__.cwl_type_map[type_name]
        #     elif type_name == "File":
        #         type_name = "string"
        #         self.file_content_type = "text/plain"
        #     elif type_name == "Directory":
        #         type_name = "string"
        #         self.file_content_type = "text/plain"
        #     else:
        #         type_name = None
        #     self.min_occurs = 1
        #     self.max_occurs = 0

        #     if not type_name:
        #         raise Exception("Unsupported type: '{0}'".format(type_name))

        #     self.type = type_name

        # elif isinstance(input.type, cwl_v1_0.InputEnumSchema):
        #     type_name = "string"
        #     self.possible_values = [str(s)[trim_len+len(self.identifier)+2:] for s in input.type.symbols]


class ProcessOutput:
    def __init__(self, identifier, title=None, description=None, input_type="string"):
        self.identifier = str(identifier)
        self.title = title or identifier
        if self.title:
            self.title = str(self.title)
        self.description = description or title
        if self.description:
            self.description = str(self.description)
        self.type = input_type
        self.min_occurs = 1
        self.max_occurs = 1
        self.default_value = None
        self.possible_values = None
        self.is_complex = False
        self.is_file = False
        self.file_content_type = None
        self.is_directory = False

    def __repr__(self):
        return f"ProcessOutput(\n\tidentifier={self.identifier}, \n\ttitle={self.title}, \n\tdescription={self.description}, \n\ttype={self.type}, \n\tmin_occurs={self.min_occurs}, \n\tmax_occurs={self.max_occurs}, \n\tdefault_value={self.default_value}, \n\tpossible_values={self.possible_values}, \n\tis_complex={self.is_complex}, \n\tis_file={self.is_file}, \n\tfile_content_type={self.file_content_type}, \n\tis_directory={self.is_directory}\n)"

    @classmethod
    def create_from_cwl(cls, output, trim_len):
        print("ProcessOutput.create_from_cwl", file=sys.stderr)
        process_output = cls(
            output.id[trim_len + 1 :],
            output.label,
            output.doc,
        )

        process_output.set_type_from_cwl(output)

        print(f"process_output = {process_output}", file=sys.stderr)

        return process_output

    def set_type_from_cwl(self, output):
        if isinstance(output.type, str):
            type_name = output.type
            if type_name == "string":
                pass
            elif type_name == "File":
                type_name = "string"
                self.file_content_type = "text/plain"
            elif type_name == "Directory":
                self.is_complex = True
                self.file_content_type = "application/json"
            else:
                raise Exception(
                    "Unsupported type for output '{0}': {1}".format(
                        output.id, type_name
                    )
                )
            self.type = type_name

        # elif isinstance(output.type, cwl_v1_0.OutputArraySchema):
        #     type_name = output.type.items

        #     if type_name == "string":
        #         pass
        #     elif type_name == "File":
        #         type_name = "string"
        #         self.file_content_type = "text/plain"
        #     elif type_name == "Directory":
        #         self.is_complex = True
        #         self.file_content_type = "application/json"
        #     else:
        #         raise Exception(
        #             "Unsupported type for output '{0}': {1}".format(
        #                 output.id, type_name
        #             )
        #         )

        #     self.min_occurs = 1
        #     self.max_occurs = 0

        #     if not type_name:
        #         raise Exception("Unsupported type: '{0}'".format(type_name))

        #     self.type = type_name


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
        print("Starting DeployService *********************************************", file=sys.stderr)
        self.conf = conf
        self.inputs = inputs
        self.outputs = outputs

        self.zooservices_folder = self.get_zoo_services_folder()
        print(f"\tzooservices_folder = {self.zooservices_folder}", file=sys.stderr)

        self.cookiecutter_configuration_file = self._get_conf_value(
            key="configurationFile", section="cookiecutter"
        )
        print(f"\tgetting cookiecutter_configuration_file: {self.cookiecutter_configuration_file}", file=sys.stderr)
        

        self.cookiecutter_templates_folder = self._get_conf_value(
            key="templatesPath", section="cookiecutter"
        )
        print(f"\tcookiecutter_templates_folder = {self.cookiecutter_templates_folder}", file=sys.stderr)

        self.cookiecutter_template_url = self._get_conf_value(
            key="templateUrl", section="cookiecutter"
        )
        print(f"\tcookiecutter_template_url = {self.cookiecutter_template_url}", file=sys.stderr)

        self.cookiecutter_template_branch = self._get_conf_value_if_exists(
            key="templateBranch", section="cookiecutter"
        )
        print(f"\tcookiecutter_template_branch = {self.cookiecutter_template_branch}", file=sys.stderr)

        self.tmp_folder = self._get_conf_value("tmpPath")
        print(f"\ttmp_folder = {self.tmp_folder}", file=sys.stderr)

        self.process_id = self.conf["lenv"]["usid"]
        print(f"\tprocess_id = {self.process_id}", file=sys.stderr)

        self.service_tmp_folder = self.create_service_tmp_folder()
        print(f"\tservice_tmp_folder = {self.service_tmp_folder}", file=sys.stderr)

        self.cwl_content = self.get_application_package()
        self.workflow_parameters = self.get_application_parameters_description()
        print(f"\tcwl_content = {self.cwl_content}", file=sys.stderr)

        if "workflow_id" in self.conf["lenv"]:
            print("\tworkflow_id found in conf", file=sys.stderr)
            print(f"\tworkflow_id = {self.conf['lenv']['workflow_id']}", file=sys.stderr)
            self.service_configuration = Process.create_from_cwl(
                cwl=self.cwl_content,
                workflow_id=self.conf["lenv"]["workflow_id"],
                workflow_parameters=self.workflow_parameters,
            )
        else:
            print("\tworkflow_id not found in conf. Using workflow_id from service_configuration.identifier", file=sys.stderr)
            self.service_configuration = Process.create_from_cwl(
                cwl=self.cwl_content,
                workflow_id=None,
                workflow_parameters=self.workflow_parameters,
            )
            print(
                f"\tworkflow_id = {self.service_configuration.identifier}",
                file=sys.stderr,
            )

        self.service_configuration.service_provider = (
            f"{self.service_configuration.identifier}.service"
        )
        print(
            f"\tservice_provider = {self.service_configuration.service_provider}",
            file=sys.stderr,
        )
        self.service_configuration.service_type = "Python"
        print(
            f"\tservice_type = {self.service_configuration.service_type}", file=sys.stderr
        )

        print(
            f"\tservice_configuration (complete Process) = {self.service_configuration}",
            file=sys.stderr,
        )

        self.conf["lenv"]["workflow_id"] = self.service_configuration.identifier
        self.conf["lenv"]["service_name"] = self.service_configuration.identifier

        print("End initializing DeployService *********************************************", file=sys.stderr)

    def get_zoo_services_folder(self):
        # checking for namespace
        if (
            "zooServicesNamespace" in self.conf
            and "namespace" in self.conf["zooServicesNamespace"]
            and "servicesNamespace" in self.conf
            and "path" in self.conf["servicesNamespace"]
        ):
            zooservices_folder = os.path.join(
                self.conf["servicesNamespace"]["path"],
                self.conf["zooServicesNamespace"]["namespace"],
            )
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
        print("creating the folder where we will download the applicationPackage", file=sys.stderr)
        tmp_path = os.path.join(self.tmp_folder, f"DeployProcess-{self.process_id}")
        try:
            print(f"Creating tmp_path: {tmp_path}", file=sys.stderr)
            os.makedirs(tmp_path, exist_ok=True)
        except Exception as e:
            print(e, file=sys.stderr)

        return tmp_path

    def get_application_package(self):
        # checking if applicationPackage exists
        if "applicationPackage" not in self.inputs.keys():
            raise ValueError("The inputs dot not include applicationPackage")

        # User is supposed to send Argo Workflow in the input
        argo_workflow = yaml.safe_load(self.inputs["applicationPackage"]["value"])

        # delete key parameters
        argo_workflow.pop("parameters", None)

        return argo_workflow

    def get_application_parameters_description(self) -> list:
        if "applicationPackage" not in self.inputs.keys():
            raise ValueError("The inputs dot not include applicationPackage")

        argo_workflow = yaml.safe_load(self.inputs["applicationPackage"]["value"])
        parameters = argo_workflow.get("parameters", [])

        return parameters

    def generate_service(self):
        print("Starting service generation *********************************************", file=sys.stderr)
        path = None
        print(f"\tconf[lenv] = {self.conf['lenv']}", file=sys.stderr)
        
        if "noRunSql" in self.conf["lenv"]:
            # This part runs on ZOO-FPM
            print("************************** This part runs on ZOO-FPM **************************", file=sys.stderr)
            print("\tnoRunSql found in conf", file=sys.stderr)

            # checking if the template location is remote or local
            print(
                f"\tcookiecutter_template_url = {self.cookiecutter_template_url}",
                file=sys.stderr,
            )

            if self.cookiecutter_template_url.endswith(".git"):
                print(
                    f"\tCloning template from {self.cookiecutter_template_url}",
                    file=sys.stderr,
                )
                template_folder = os.path.join(
                    self.cookiecutter_templates_folder,
                    Path(self.cookiecutter_template_url).stem,
                )

                # checking if template had already been cloned
                print("\tchecking if template had already been cloned", file=sys.stderr)
                if os.path.isdir(template_folder):
                    print(f"\tremoving template folder: {template_folder}", file=sys.stderr)
                    shutil.rmtree(template_folder)

                # retrieving the branch to clone
                # if no branch is specified, we will clone the master branch
                print(
                    f"\tcookiecutter_template_branch = {self.cookiecutter_template_branch}",
                    file=sys.stderr,
                )
                cookiecutter_template_branch = self.cookiecutter_template_branch

                # cloning the template
                print(
                    f"Cloning template from {self.cookiecutter_template_url}",
                    file=sys.stderr,
                )
                if cookiecutter_template_branch is not None:
                    os.system(
                        f"git clone -b {cookiecutter_template_branch} {self.cookiecutter_template_url} {template_folder}"
                    )
                else:
                    os.system(
                        f"git clone {self.cookiecutter_template_url} {template_folder}"
                    )

            else:
                raise ValueError(
                    f"{self.cookiecutter_template_url} is not a valid git repo"
                )

            cookiecutter_values = {
                "service_name": self.service_configuration.identifier,
                "workflow_id": self.service_configuration.identifier,
                "conf": self.conf["cookiecutter"],
            }

            # Create project from template
            print(f"Creating project from template {template_folder}", file=sys.stderr)
            path = cookiecutter(
                template_folder,
                extra_context=cookiecutter_values,
                output_dir=self.service_tmp_folder,
                no_input=True,
                overwrite_if_exists=True,
                config_file=self.cookiecutter_configuration_file,
            )
            print("Cookiecutter done", file=sys.stderr)
            print(f"path = {path}", file=sys.stderr)
            path_files_and_dirs = os.listdir(path)
            print(f"files_and_dirs on path = {path_files_and_dirs}", file=sys.stderr)
            print("************************** End part that runs on ZOO-FPM **************************", file=sys.stderr)

        if "metadb" not in self.conf:
            print("metadb not found in conf", file=sys.stderr)
            zcfg_file = os.path.join(
                self.zooservices_folder, f"{self.service_configuration.identifier}.zcfg"
            )
            print(f"writting zcfg file: {zcfg_file}", file=sys.stderr)
            with open(zcfg_file, "w") as file:
                self.service_configuration.write_zcfg(file)

        # checking if service had already been deployed previously
        # if yes, delete it before redeploy the new one
        print(
            "checking if service had already been deployed previously", file=sys.stderr
        )
        old_service = os.path.join(
            self.zooservices_folder, self.service_configuration.identifier
        )
        if os.path.isdir(old_service):
            print(f"removing old service: {old_service}", file=sys.stderr)
            shutil.rmtree(old_service)
            if "metadb" not in self.conf:
                print(f"removing zcfg file: {zcfg_file}", file=sys.stderr)
                os.remove(zcfg_file)

        if "metadb" in self.conf and not (
            "noRunSql" in self.conf["lenv"] and self.conf["lenv"]["noRunSql"] != "false"
        ):
            print("\tmetadb found in conf and noRunSql not found in conf", file=sys.stderr)
            print("************************** This part runs on ZOO-Kernel **************************", file=sys.stderr)
            print(
                f"Running SQL for {self.service_configuration.identifier}",
                file=sys.stderr,
            )
            rSql = self.service_configuration.run_sql(conf=self.conf)
            if not (rSql):
                return False
            
            print("************************** End SQL ZOO-Kernel **************************", file=sys.stderr)

        print(f"Starting part to copy generated service.py to {self.zooservices_folder}", file=sys.stderr)
        print(f"path = {path}", file=sys.stderr)
        if path is not None:
            print(f"files_and_dirs on path before = {os.listdir(path)}", file=sys.stderr)

            print(f"Copying app-package.cwl to path {path}", file=sys.stderr)
            app_package_file = os.path.join(
                path,
                "app-package.cwl",
            )

            print(f"files_and_dirs on path after1 = {os.listdir(path)}", file=sys.stderr)

            print("***********************************", file=sys.stderr)
            print(f"service_tmp_folder = {self.service_tmp_folder}", file=sys.stderr)
            print(f"path = {path}", file=sys.stderr)
            print(f"app_package_file = {app_package_file}", file=sys.stderr)
            print("***********************************", file=sys.stderr)

            argo_workflow = yaml.safe_load(self.inputs["applicationPackage"]["value"])
            print(f"writing argo_workflow file: {app_package_file}", file=sys.stderr)
            with open(app_package_file, "w") as file:
                # yaml.dump(self.cwl_content, file)
                yaml.dump(argo_workflow, file)

            print(f"files_and_dirs on path after2 = {os.listdir(path)}", file=sys.stderr)

            print(f"moving {path} to {self.zooservices_folder}", file=sys.stderr)
            shutil.move(path, self.zooservices_folder)

            print(f"files_and_dirs on {self.zooservices_folder} after moving = {os.listdir(self.zooservices_folder)}", file=sys.stderr)

            print(f"removing tmp folder {self.service_tmp_folder}", file=sys.stderr)
            # shutil.rmtree(self.service_tmp_folder)

        self.conf["lenv"]["deployedServiceId"] = self.service_configuration.identifier
        print(
            f"deployedServiceId = {self.conf['lenv']['deployedServiceId']}",
            file=sys.stderr,
        )

        print("Service successfully deployed", file=sys.stderr)
        print("End service generation *********************************************", file=sys.stderr)
        return True


def duplicateMessage(conf, deploy_process):
    sLocation = (
        conf["openapi"]["rootUrl"]
        + "/processes/"
        + deploy_process.service_configuration.identifier
    )
    if "headers" in conf:
        conf["headers"]["Location"] = sLocation
    else:
        conf["headers"] = {"Location": sLocation}
    conf["lenv"]["code"] = "DuplicatedProcess"
    conf["lenv"]["message"] = zoo._(
        "A service with the same identifier is already deployed"
    )
    return zoo.SERVICE_FAILED


def check_k8s_connection(conf):
    print("Checking connection to kubernetes cluster", file=sys.stderr)
    try:
        from kubernetes import config, client
        print("Import kubernetes successful", file=sys.stderr)

        # setting the environment variables
        print("Setting environment variables", file=sys.stderr)
        try:
            print("conf = ", file=sys.stderr)
            print(json.dumps(conf, indent=2), file=sys.stderr)
            print("env = ", file=sys.stderr)
            print(os.environ, file=sys.stderr)
        except Exception as e:
            print(e, file=sys.stderr)

        os.environ["KUBERNETES_SERVICE_HOST"] = conf["renv"]["KUBERNETES_SERVICE_HOST"]
        os.environ["KUBERNETES_SERVICE_PORT"] = conf["renv"]["KUBERNETES_SERVICE_PORT"]

        print(f"KUBERNETES_SERVICE_HOST = {os.environ['KUBERNETES_SERVICE_HOST']}", file=sys.stderr)
        print(f"KUBERNETES_SERVICE_PORT = {os.environ['KUBERNETES_SERVICE_PORT']}", file=sys.stderr)

        # remove HTTP_PROXY from the environment
        os.environ.pop("HTTP_PROXY", None)
        print("HTTP_PROXY removed from environment", file=sys.stderr)

        # Load the kube config from the default location
        # config.load_kube_config()
        # config.load_config()
        config.load_incluster_config()
        print("Connection to kubernetes cluster successful", file=sys.stderr)
        v1 = client.CoreV1Api()
        print("Listing pods with their IPs:", file=sys.stderr)
        ret = v1.list_pod_for_all_namespaces(watch=False)
        for i in ret.items:
            print("%s\t%s\t%s" % (i.status.pod_ip, i.metadata.namespace, i.metadata.name), file=sys.stderr)

    except Exception as e:
        print("Error while checking connection to kubernetes cluster", file=sys.stderr)
        print(e, file=sys.stderr)
    finally:
        print("End check kubernetes cluster connection", file=sys.stderr)


def DeployProcess(conf, inputs, outputs):
    try:
        if (
            "applicationPackage" in inputs.keys()
            and "isArray" in inputs["applicationPackage"].keys()
            and inputs["applicationPackage"]["isArray"] == "true"
        ):
            for i in range(int(inputs["applicationPackage"]["length"])):
                lInputs = {
                    "applicationPackage": {
                        "value": inputs["applicationPackage"]["value"][i]
                    }
                }
                lInputs["applicationPackage"]["mimeType"] = inputs[
                    "applicationPackage"
                ]["mimeType"][i]
                print(f"************************* Deploying service {i} *************************", file=sys.stderr)
                deploy_process = DeployService(conf, lInputs, outputs)
                res = deploy_process.generate_service()
                if not (res):
                    return duplicateMessage(conf, deploy_process)
        else:
            print("************************* Deploying service *************************", file=sys.stderr)
            deploy_process = DeployService(conf, inputs, outputs)

            res = deploy_process.generate_service()

            if not (res):
                return duplicateMessage(conf, deploy_process)

        response_json = {
            "message": f"Service {deploy_process.service_configuration.identifier} version {deploy_process.service_configuration.version} successfully deployed.",
            "service": deploy_process.service_configuration.identifier,
            "status": "success",
        }

        print(
            f"Service {deploy_process.service_configuration.identifier} version {deploy_process.service_configuration.version} successfully deployed.",
            file=sys.stderr,
        )
        print(f"response = {json.dumps(response_json, indent=2)}", file=sys.stderr)
        outputs["Result"]["value"] = json.dumps(response_json)
        print(f"outputs = {json.dumps(outputs, indent=2)}", file=sys.stderr)
        return zoo.SERVICE_DEPLOYED
    except Exception as e:
        print("Exception in Python service", file=sys.stderr)
        print(e, file=sys.stderr)
        conf["lenv"]["message"] = str(e)
        return zoo.SERVICE_FAILED
