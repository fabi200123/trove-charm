import collections
import os

import charmhelpers.core.hookenv as hookenv
import charms_openstack.charm
import charms_openstack.ip as os_ip


PACKAGES = [
    'trove-api',
    'trove-conductor',
    'trove-taskmanager',
]

TROVE_SERVICES = [
    'trove-api',
    'trove-conductor',
    'trove-taskmanager',
]

TROVE_API_PORT = 8779
TROVE_DIR = '/etc/trove'
TROVE_CONF = os.path.join(TROVE_DIR, 'trove.conf')
TROVE_PASTE_API = os.path.join(TROVE_DIR, 'api-paste.ini')


class TroveCharm(charms_openstack.charm.HAOpenStackCharm):

    # Internal name of charm
    service_name = name = 'trove'

    # First release supported
    release = 'yoga'

    # List of packages to install for this charm
    packages = PACKAGES

    api_ports = {
        'trove-api': {
            os_ip.PUBLIC: TROVE_API_PORT,
            os_ip.ADMIN: TROVE_API_PORT,
            os_ip.INTERNAL: TROVE_API_PORT,
        }
    }

    service_type = 'database'
    default_service = 'trove-api'
    services = ['haproxy'] + TROVE_SERVICES
    sync_cmd = ['trove-manage', 'db_sync']

    required_relations = ['shared-db', 'amqp', 'identity-service']

    restart_map = {
        TROVE_CONF: services,
        TROVE_PASTE_API: [default_service],
    }

    ha_resources = ['vips', 'haproxy']

    release_pkg = 'trove-common'

    package_codenames = {
        'trove-common': collections.OrderedDict([
            ('2', 'mitaka'),
            ('3', 'newton'),
            ('4', 'ocata'),
        ]),
    }

    def get_amqp_credentials(self):
        return ('database', 'database')

    def get_database_setup(self):
        return [
            {
                'database': 'database',
                'username': 'database',
                'hostname': hookenv.unit_private_ip(),
            },
        ]
