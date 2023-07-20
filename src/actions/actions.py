#!/usr/bin/env python3
# Copyright 2023 Cloudbase Solutions
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import subprocess
import sys

# Load modules from $CHARM_DIR/lib
sys.path.append('lib')

from charms.layer import basic
basic.bootstrap_charm_deps()
basic.init_config_states()

from charms import reactive
from charmhelpers.core import hookenv
import requests


def load_datastore_cfg_params_action(*args):
    """Runs trove-manage db_load_datastore_config_parameters on controller."""
    if not reactive.all_flags_set('identity-service.available',
                                  'shared-db.available',
                                  'amqp.available'):
        return hookenv.action_fail(
            'all required relations are not available, please defer action '
            'until deployment is complete.'
        )

    action_args = hookenv.action_get()

    # Download the config file from the URL and save it in /tmp.
    config_file_url = action_args["config-file"]
    resp = requests.get(config_file_url)
    config_file_path = os.path.join("/tmp", os.path.basename(config_file_url))
    with open(config_file_path, "wb") as f:
        f.write(resp.content)

    subprocess_args = [
        "trove-manage",
        "db_load_datastore_config_parameters",
        action_args["datastore"],
        action_args["datastore-version-name"],
        config_file_path,
    ]
    if action_args.get("version"):
        subprocess_args += ["--version", action_args["version"]]

    return subprocess.check_call(subprocess_args)


# Actions to function mapping, to allow for illegal python action names that
# can map to a python function.
ACTIONS = {
    "db-load-datastore-config-params": load_datastore_cfg_params_action,
}


def main(args):
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        return f"Action {action_name} undefined"
    else:
        try:
            action(args)
        except Exception as e:
            hookenv.action_fail(str(e))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
