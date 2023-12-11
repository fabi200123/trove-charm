## Trove Instalation

### Objectives

This document provides a step-by-step guide for installation of Trove with an existing OpenStack environment.

### Requirements

A running OpenStack environment installed on Ubuntu 20.04 or 22.04 LTS is required, including the following components:

- Compute (Nova)
- Image Service (Glance)
- Identity (Keystone)
- Network (Neutron)
- If you want to provision databases on block-storage volumes, you also need Block Storage (Cinder)
- If you want to do backup/restore or replication, you also need Object Storage (Swift)
- AMQP service (RabbitMQ or QPID)
- MySQL (SQLite, PostgreSQL) database

### Networking requirements

The Trove database instances are spawned with 2 NICs attached to them, one for the `tenant network`, and one for the `management network`. The instances have Trove guest agents running in them, which are supposed to connect to the Trove control plane through AMQP using the management NIC. In a typical Juju OpenStack deployment, they should be able to connect to the same RabbitMQ units as the Trove control plane. In addition to that, the subnet allocated for Trove instances need to be sufficiently large enough to allow the maximum number of instances and controllers likely to be deployed throughout the lifespan of the cloud.

Below is a networking setup example:

```
     ┌────────────────────────────┐   ┌──────────────────────────┐
     │ Control Plane              │   │ Compute Node             │
     │ ┌────────────────────────┐ │   │ ┌──────────────────────┐ │
     │ │ LXD                    │ │   │ │ KVM                  │ │
     │ │ ┌──────────┐ ┌───────┐ │ │   │ │ ┌──────────────────┐ │ │
     │ │ │ RabbitMQ │ │ Trove │ │ │   │ │ │  Trove instance  │ │ │
     │ │ └──┬───────┘ └──┬────┘ │ │   │ │ ├────┐        ┌────┤ │ │
     │ │    │            │      │ │   │ │ │eth0│        │eth1│ │ │
     │ └────┼────────────┼──────┘ │   │ │ └──┬─┴────────┴──┬─┘ │ │
     │      ├────────────┘        │   │ └────┼─────────────┼───┘ │
     │ ┌────┴──┐ ┌──────┐ ┌─────┐ │   │   ┌──┴───┐    ┌────┴───┐ │
     │ │br-eth0│ │br-int├─┤br-ex│ │   │   │br-int├─┐  │br-trove│ │
     │ └──┬────┘ └──┬───┘ └───┬─┘ │   │   └──────┘ │  └─────┬──┘ │
     │ ┌──┴─┐    ┌──┴─┐    ┌──┴─┐ │   │ ┌────┐   ┌─┴──┐   ┌─┴──┐ │   ┌──────────┐
     │ │eth0│    │eth1│    │eth2│ │   │ │eth0│   │eth1│   │eth2│ │   │          │
     │ └──┬─┘    └──┬─┘    └──┬─┘ │   │ └──┬─┘   └──┬─┘   └──┬─┘ │   │  Router  │
     │    │         │         │   │   │    │        │        │   │   │          │
     └────┼─────────┼─────────┼───┘   └────┼────────┼────────┼───┘   └─┬──────┬─┘
          │         │         │            │        │        │         │      │
mgmt-net  │         │         │            │        │        │         │      │
──────────┴─────────┼─────────┼────────────┴────────┼────────┼─────────┴──────┼───
                    │         │                     │        │                │
tenant-net          │         │                     │        │                │
────────────────────┴─────────┼─────────────────────┴────────┼────────────────┼───
                              │                              │                │
public-net                    │                              │                │
──────────────────────────────┴──────────────────────────────┼────────────────┼───
                                                             │                │
trove-net                                                    │                │
─────────────────────────────────────────────────────────────┴────────────────┴───
```

- `mgmt-net`: Network used for managing the Nodes and OpenStack services in the LXD units.
- `tenant-net`: Network dedicated for guest VM networks.
- `public-net`: Public network used for external access and floating IPs.
- `trove-net`: Management network to be used by Trove, which is routed to the `mgmt-net`. IPs in this subnet are managed by Neutron.

A Neutron flat network needs to be defined for `trove-net` with a subnet CIDR that is being routed to the Juju management network (`mgmt-net`):

```bash
# Add a new flat network provider to neutron API charm, if not added already.
# They are separated by space.
# We're adding physnet2.
juju config neutron-api flat-network-providers="physnet1 physnet2"

# If Neutron OVS is being used:
juju config neutron-gateway bridge-mappings="physnet1:br-ex physnet2:br-trove" data-port="br-ex:eth2 br-trove:eth3"
juju config neutron-openvswitch bridge-mappings="physnet2:br-trove" data-port="br-trove:eth2"

# Define the flat OpenStack network and subnet.
openstack network create --share --provider-network-type=flat \
  --provider-physical-network=physnet2 --description "Trove management network" trove-net

# We specify --gateway=none so it will not create 2 default routes
openstack subnet create --subnet-range=10.8.102.0/24 --gateway=none \
  --host-route destination=10.8.11.0/24,gateway=10.8.102.1 \
  --network trove-net trove-subnet
```

The Neutron network created above will be used to configure the Trove charm, which will be covered in the [Configuration Options](#Configuration-Options) section.

You must also create a Neutron security group which will be applied to trove instance port created on the management network. The cloud admin has full control of the security group, e.g it can be helpful to allow SSH access to the trove instance from the controller for troubleshooting purposes (ie. TCP port 22), though this is not strictly necessary in production environments. This can be set through a Trove charm config option (see [Configuration Options](#Configuration-Options) section).

Finally, you need to add routing or interfaces to this network so that the Trove controller is able to communicate with Nova servers on this network.


### Building the Trove Charm

In order to build the Trove charm, execute the following steps:

- Install requirement for charm building:

```bash
sudo snap install charmcraft --classic
```

- Clone the repository:

```bash
git clone https://github.com/cloudbase/trove-charm
cd trove-charm
```

- Build the charm:

```bash
tox -e build
```

Alternatively, you can install the charm snap and build the charm:

```bash
sudo snap install charm --classic
tox -e build-reactive
```

**NOTE:** The charm should have been built in `./trove_ubuntu-22.04-amd64.charm`, or in `./build/trove` if the charm was built with the `charm` building tools instead of `charmcraft`. This charm path will be used to deploy or refresh the Trove charm.

To replace the current Trove charm with a newer revision and keeping the existing relations and configuration, run the following command:

```bash
juju refresh --path ./trove_ubuntu-22.04-amd64.charm trove
```

In order for the Trove charm to become **Active**, the `management-network` config option needs to be set with the network UUID created above. See the [Configuration Options](#Configuration-Options) section.

For more details on the Management Network needed by Trove, check [here](https://docs.openstack.org/trove/latest/admin/run_trove_in_production.html#management-network).

After the Trove charm has become **Active**, you can check that it can be accessed by running:

```bash
# Load the OpenStack credentials.
. ~/admin-openrc.sh

# This requires python-troveclient to be installed.
openstack database instance list
```

There should be no errors while running the command above.


### Build the Trove Image

When Trove receives a command to create a database instance, it does so by launching a Nova instance based on the appropriate guest image that is stored in Glance.

#### Operating System

The officially supported operating system is Ubuntu, based on which the functional tests are running.

#### Docker

Since Vitoria, the database service is running as docker container inside the trove guest instance, so `docker` should be installed when building the guest image. This also means the trove guest instance should be able to pull docker images from the image registry (either from user port or trove management port), the related options for container images are:

```bash
[mysql]
docker_image
backup_docker_image

[postgresql]
docker_image
backup_docker_image

[mariadb]
docker_image
backup_docker_image
```

#### Trove Guest Agent

The guest agent runs inside the Nova instances that are used to run the database engines. The agent listens to the messaging bus for the topic and is responsible for actually translating and executing the commands that are sent to it by the task manager component for the particular datastore.

Trove guest agent is responsible for datastore docker container management.

#### Injected Configuration for the Guest Agent

When TaskManager launches the guest VM it injects config files into the VM, including:

- `/etc/trove/conf.d/guest_info.conf`: Contains some information about the guest, e.g. the guest identifier, the tenant ID, etc.
- `/etc/trove/conf.d/trove-guestagent.conf`: The config file for the guest agent service.

**NOTE:** In addition to these config files, Trove supports to inject user data when launching the instance for customization on boot time, e.g. network configuration, hosts file settings, etc. The user data files are located inside the directory configured by `cloudinit_location`, for mysql, the file name is `mysql.cloudinit`.

#### Building Guest Images using trovestack

`trovestack` is the recommended tooling provided by Trove community to build the guest images. Before running `trovestack` command, clone the trove repository:

```bash
git clone https://opendev.org/openstack/trove
cd trove/integration/scripts
```

The trove guest image could be created by running the following command:

```bash
./trovestack build-image \
   {guest_os} \
   {guest_os_release} \
   {dev_mode} \
   {guest_username} \
   {output_image_path}
```

- Currently, only `guest_os=ubuntu` and `guest_os_release=jammy` are fully tested and supported.

- Default input values:

```bash
guest_os=ubuntu
guest_os_release=jammy
dev_mode=true
guest_username=ubuntu
output_image_path=$HOME/images/trove-guest-${guest_os}-${guest_os_release}-dev.qcow2
```

- `dev_mode=true` is mainly for testing purpose for trove developers and it's necessary to build the image on the trove controller host, because the host and the guest VM need to ssh into each other without password. In this mode, when the trove guest agent code is changed, the image doesn't need to be rebuilt which is convenient for debugging. Trove guest agent will ssh into the controller node and download trove code during the service initialization.

- If `dev_mode=false`, the trove code for guest agent is injected into the image at the building time.

- Some other global variables:
  - `HOST_SCP_USERNAME`: Only used in dev mode, this is the user name used by guest agent to connect to the controller host, e.g. in devstack environment, it should be the `stack` user.

- The image type can be easily changed by specifying a different image file extension, e.g. to build a raw image, you can specify `$your-image-name.raw` as the `output_image_path` parameter.

For example, in order to build a guest image for Ubuntu jammy operating system in development mode:

```bash
./trovestack build-image ubuntu jammy true ubuntu
```

**NOTE:** For more details about building an image and actual images, see [building guest images](https://docs.openstack.org/trove/latest/admin/building_guest_images.html) guide.

#### Register the Trove image in Glance

Once the image build is finished, the cloud administrator needs to register the image in Glance and register a new datastore or version in Trove using `trove-manage` command, e.g. after building an image for MySQL 5.7.29:

```bash
openstack image create trove-guest-ubuntu-jammy \
  --private \
  --disk-format qcow2 \
  --container-format bare \
  --tag trove --tag mysql \
  --file ~/images/trove-guest-ubuntu-jammy-dev.qcow2

# Declare a datastore.
openstack datastore version create 5.7.29 mysql mysql "" \
  --image-tags trove,mysql \
  --active --default

CONF_FILE_URL=${trove_repo_dir}/trove/templates/mysql/validation-rules.json
juju run --wait trove/leader db-load-datastore-config-params \
  datastore=mysql datastore-version-name=5.7.29 config-file=$CONF_FILE_URL
```

**NOTE:** The command `trove-manage` needs to run on Trove controller node.

#### (Optional) Get a Trove image built by the community

Instead of building your own Trove image, a community built image can be used:

```bash
# Download an image built by the community.
# For more images and how to build them, see https://docs.openstack.org/trove/latest/admin/building_guest_images.html
wget https://tarballs.opendev.org/openstack/trove/images/trove-zed-guest-ubuntu-focal.qcow2
openstack image create trove-zed-guest-ubuntu-focal \
  --private \
  --disk-format qcow2 \
  --container-format bare \
  --tag trove --tag mysql \
  --file ./trove-zed-guest-ubuntu-focal.qcow2

# Declare a datastore.
openstack datastore version create 5.7.29 mysql mysql "" \
  --image-tags trove,mysql \
  --active --default

# Load the validation rules for the datastore.
CONF_FILE_URL="https://github.com/openstack/trove/blob/stable/zed/trove/templates/mysql/validation-rules.json"
juju run --wait trove/leader db-load-datastore-config-params \
  datastore=mysql datastore-version-name=5.7.29 config-file=$CONF_FILE_URL
```

#### Quota Management

The amount of resources that could be created by each OpenStack project is controlled by quota. The default trove resource quota for each project is set in Trove config file as follows unless changed by the cloud administrator via [Quota API](https://docs.openstack.org/api-ref/database/#update-resources-quota-for-a-specific-project).

```bash
[DEFAULT]
max_instances_per_tenant = 10
max_backups_per_tenant = 50
```

### Configuration Options

The Trove charm needs the `management-networks` config option in order to become **active**. It needs to be set to the Neutron network created in the [Networking Requirements](#networking-requirements) setup section:

```bash
juju config trove management-networks=$TROVE_NET_UID
```

A management Neutron security group can be created and assigned to the management ports of the Trove instances by setting the `management-security-groups` config option:

```bash
openstack security group create trove-sg --description "Trove Security Group" --tag "trove-charm"
openstack security group rule create trove-sg --dst-port 22 --protocol tcp --ingress --ethertype ipv4
juju config trove management-security-groups=$TROVE_SG_UID
```

The security group above adds a SSH ingress rule. The Trove instances will need an SSH keypair:

```bash
# Get the Trove user ID.
openstack user list --project services

# Create the keypair for the Trove user ID.
openstack keypair create --user $TROVE_USER_ID --public-key ~/.ssh/id_rsa.pub trove-keypair

# Configure Trove to spawn instances with the SSH keypair.
juju config trove nova-keypair=trove-keypair
```

### Create and access a database instance

#### Before creating the instance

- Choose the flavor. A flavor defines RAM and root volume size for the instance. Trove OpenStack CLI provides a command to get a flavor list that are supported to create trove instance.

```bash
openstack database flavor list
```

- Choose a neutron network that the instance is allocated IP address from. You can either specify the network ID or the subnet ID, you can even specify the IP address (must be available).

- Choose the volume size. The cinder volume is used as data storage for the database.

- Choose datastore version.

- (Optional) Choose the data source. You can create a new instance by restoring a backup using `--backup <BACKUP_ID>`, or create a replica instance for a replication cluster using `--replica-of <PRIMARY_INSTANCE_ID>`

**NOTE:** If creating instance as a replica for the replication cluster, flavor is not needed as it's the same with the replication primary.

#### Create a database instace

Now, you can create a database instances:

```bash
openstack database instance create mysql_instance_1 \
  --flavor m1.large \
  --size 3 \
  --nic net-id=$TENANT_NET_UUID \
  --databases test --users userA:Passw0rd \
  --datastore mysql --datastore-version 5.7.29 \
  --is-public \
  --allowed-cidr $TENANT_NET_CIDR
```

It should return something like this:

```bash
+--------------------------+--------------------------------------+          
| Field                    | Value                                |
+--------------------------+--------------------------------------+
| allowed_cidrs            | ['192.168.0.0/24']                   |
| created                  | 2023-11-27T14:11:55                  |
| datastore                | mysql                                |
| datastore_version        | 5.7.29                               |
| datastore_version_number | 5.7.29                               |
| encrypted_rpc_messaging  | True                                 |
| flavor                   | 82e09dd9-fa54-4ee6-b538-767d7b24929b |
| id                       | 52b79d05-492d-4d99-9e7e-c01097d63e0b |
| name                     | mysql_instance_1                     |
| operating_status         |                                      |
| public                   | True                                 |
| region                   | RegionOne                            |
| server_id                | None                                 |
| service_status_updated   | 2023-11-27T14:11:55                  |
| status                   | BUILD                                |
| tenant_id                | 797c7519dcbb40a48096bd5feabe8c66     |
| updated                  | 2023-11-27T14:11:55                  |
| volume                   | 3                                    |
| volume_id                | None                                 |
+--------------------------+--------------------------------------+
```

To check that the instances become **ACTIVE**, run the following command:

```bash
openstack database instance list
```

#### Get the IP address of the database instance

Wait until the instance `operating_status` changes to **HEALTHY** before getting IP address to access the database:

```bash
openstack database instance show mysql_instance_1

+--------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| Field                    | Value                                                                                                                                              |
+--------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------+
| addresses                | [{'address': '192.168.0.171', 'type': 'private', 'network': '97a0a9e6-7724-433e-a695-16f3cc3f45e0'}, {'address': '10.8.12.189', 'type': 'public'}] |
| allowed_cidrs            | ['192.168.0.0/24']                                                                                                                                 |
| created                  | 2023-11-27T14:11:55                                                                                                                                |
| datastore                | mysql                                                                                                                                              |
| datastore_version        | 5.7.29                                                                                                                                             |
| datastore_version_number | 5.7.29                                                                                                                                             |
| flavor                   | 82e09dd9-fa54-4ee6-b538-767d7b24929b                                                                                                               |
| id                       | fe8f7cf6-e10f-4267-9dce-c072049a6aac                                                                                                               |
| ip                       | 192.168.0.171, 10.8.12.189                                                                                                                         |
| name                     | mysql_instance_1                                                                                                                                   |
| operating_status         | HEALTHY                                                                                                                                            |
| public                   | True                                                                                                                                               |
| region                   | RegionOne                                                                                                                                          |
| service_status_updated   | 2023-11-27T14:11:55                                                                                                                                |
| status                   | ACTIVE                                                                                                                                             |
| updated                  | 2023-11-27T14:13:08                                                                                                                                |
| volume                   | 3                                                                                                                                                  |
| volume_id                | 8a2023af-ab70-4665-b080-d5f6fe3b8681                                                                                                               |
+--------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+
```


#### Access the new database

You can now access the new database you just created by using typical database access commands. In this MySQL example, replace IP_ADDRESS with the correct IP address according to where the command is running. Make sure your IP address is in the allowed CIDRs specified in the above command.

```bash
mysql -h IP_ADDRESS -uuserA -ppassword
```

### Manage databases and users on Trove instances

Assume that you installed Trove service and uploaded images with datastore of your choice. This section shows how to manage users and databases in a MySQL 5.7 instance.

Currently, the Database and User API is only supported by mysql datastore.

For database user management, there are two approaches:

  1. If the `root_on_create` option is enabled for the datastore in trove service config file, the root user password is returned after creating instance, which can be used directly to access the database.

  2. If `root_on_create=False`, the recommended way is to get root password (`POST /v1.0/{project_id}/instances/{instance_id}/root` or `openstack database root enable` in CLI) and communicate with the database service directly for database and user management.

#### Manage root user

For all the datastores, the user could enable root and get root password for further database operations.

```bash
openstack database root enable <instance_id>
+----------+--------------------------------------+
| Field    | Value                                |
+----------+--------------------------------------+
| name     | root                                 |
| password | I5nPpBj1qf1eGR1idQorj1szppXGpYyYNj4h |
+----------+--------------------------------------+
```

**NOTE:** If needed, `openstack database root disable <instance_id>` command could disable the root user.

#### Database and User management via Trove CLI

Trove provides API to manage users and databases for mysql datastore.

```bash
openstack database user list db-instance
+------+------+-----------+
| Name | Host | Databases |
+------+------+-----------+
| test | %    | testdb    |
+------+------+-----------+
```

```bash
openstack database user create db-instance newuser userpass --databases testdb
openstack database user list db-instance
+---------+------+-----------+
| Name    | Host | Databases |
+---------+------+-----------+
| newuser | %    | testdb    |
| test    | %    | testdb    |
+---------+------+-----------+
```

```bash
mysql -h IP_ADDRESS -u newuser -p testdb
Enter password:
mysql> show databases;
+--------------------+
| Database           |
+--------------------+
| information_schema |
| testdb             |
+--------------------+
2 rows in set (0.00 sec)
```

```bash
openstack database db create db-instance newdb
openstack database db list db-instance
+--------+
| Name   |
+--------+
| newdb  |
| sys    |
| testdb |
+--------+
```

```bash
mysql -h IP_ADDRESS -u newuser -p newdb
Enter password:
ERROR 1044 (42000): Access denied for user 'newuser'@'%' to database 'newdb'
```

### Delete databases

Lastly, Trove provides API for deleting databases.

```bash
openstack database db list db-instance
+--------+
| Name   |
+--------+
| newdb  |
| sys    |
| testdb |
+--------+
```

Delete the `testdb` database:

```bash
openstack database db delete db-instance testdb

openstack database db list db-instance
+--------+
| Name   |
+--------+
| newdb  |
| sys    |
+--------+
```

Check that the database was indeed deleted:

```bash
mysql -h IP_ADDRESS -u test -p testdb
Enter password:
ERROR 1049 (42000): Unknown database 'testdb'
```

### Backup and restore a database

You can use Database services to backup a database and store the backup artifact in the Object Storage service. Later on, if the original database is damaged, you can use the backup artifact to restore the database. The restore process creates a new database instance.

The backup data is stored in OpenStack Swift, the user is able to customize which container to store the data. The following ways are described in the order of precedence from greatest to least:

1. The container name can be specified when creating backups, this could override either the backup strategy setting or the default setting in Trove configuration.

2. Users could create backup strategy either for the project scope or for a particular instance.

3. If not configured by the end user, will use the default value in Trove configuration.

**NOTE:** If the objects in the backup container are manually deleted, the database can't be properly restored.

#### Before creating backup

- Make sure you have created an instance, e.g. in this example, we use the following instance:

```bash
+--------------------------------------+------------------+-----------+-------------------+--------+------------------+--------+----------------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------+------+------+
| ID                                   | Name             | Datastore | Datastore Version | Status | Operating Status | Public | Addresses                                                                                                                                          | Flavor ID                            | Size | Role |
+--------------------------------------+------------------+-----------+-------------------+--------+------------------+--------+----------------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------+------+------+
| 78e338e3-d1c4-4189-8ea7-bfc1fab5011f | mysql_instance_1 | mysql     | 5.7.29            | ACTIVE | HEALTHY          | True   | [{'address': '192.168.0.171', 'type': 'private', 'network': '97a0a9e6-7724-433e-a695-16f3cc3f45e0'}, {'address': '10.8.12.189', 'type': 'public'}] | 82e09dd9-fa54-4ee6-b538-767d7b24929b |    3 |      |
+--------------------------------------+------------------+-----------+-------------------+--------+------------------+--------+----------------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------+------+------+
```

- Optionally, create a backup strategy for the instance. You can also specify a different swift container name (`--swift-container`) when creating the backup.

```bash
openstack database backup strategy create --instance-id 78e338e3-d1c4-4189-8ea7-bfc1fab5011f --swift-container my-trove-backups
+-----------------+--------------------------------------+
| Field           | Value                                |
+-----------------+--------------------------------------+
| backend         | swift                                |
| instance_id     | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f |
| project_id      | fc51186c63df417ea63cec6c65a2d564     |
| swift_container | my-trove-backups                     |
+-----------------+--------------------------------------+
```

#### Backup the database instance

Back up the database instance by using the `openstack database backup create` command. In this example, the backup is called `mysql-backup-name1`.

```bash
openstack database backup create mysql-backup-name1 --instance mysql1 --swift-container 'my-trove-backups'
+----------------------+--------------------------------------+
| Field                | Value                                |
+----------------------+--------------------------------------+
| created              | 2023-11-27T14:17:55                  |
| datastore            | mysql                                |
| datastore_version    | 5.7.29                               |
| datastore_version_id | 324f2bdf-6099-4754-a5f9-82abee026a19 |
| description          | None                                 |
| id                   | 1ecd0a75-e4aa-400b-b0c8-cb738944fd43 |
| instance_id          | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f |
| locationRef          | None                                 |
| name                 | mysql-backup-name1                   |
| parent_id            | None                                 |
| project_id           | fc51186c63df417ea63cec6c65a2d564     |
| size                 | None                                 |
| status               | NEW                                  |
| updated              | 2023-11-27T14:17:55                  |
+----------------------+--------------------------------------+
```

Later on, use either `openstack database backup list` command or `openstack database backup show` command to check the backup status:

```bash
openstack database backup list
+--------------------------------------+--------------------------------------+------------------------------+-----------+--------------------------------------+---------------------+----------------------------------+
| ID                                   | Instance ID                          | Name                         | Status    | Parent ID                            | Updated             | Project ID                       |
+--------------------------------------+--------------------------------------+------------------------------+-----------+--------------------------------------+---------------------+----------------------------------+
| 1ecd0a75-e4aa-400b-b0c8-cb738944fd43 | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f | mysql-backup-name1           | COMPLETED | None                                 | 2022-10-24T01:46:55 | fc51186c63df417ea63cec6c65a2d564 |
+--------------------------------------+--------------------------------------+------------------------------+-----------+--------------------------------------+---------------------+----------------------------------+
```

```bash
openstack database backup show 1ecd0a75-e4aa-400b-b0c8-cb738944fd43
+----------------------+---------------------------------------------------------------------------------+
| Field                | Value                                                                           |
+----------------------+---------------------------------------------------------------------------------+
| created              | 2023-11-27T14:17:55                                                             |
| datastore            | mysql                                                                           |
| datastore_version    | 7.5.29                                                                          |
| datastore_version_id | 324f2bdf-6099-4754-a5f9-82abee026a19                                            |
| description          | None                                                                            |
| id                   | 1ecd0a75-e4aa-400b-b0c8-cb738944fd43                                            |
| instance_id          | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f                                            |
| locationRef          | http://192.../my-trove-backups/1ecd0a75-e4aa-400b-b0c8-cb738944fd43.xbstream.gz |
| name                 | mysql-backup-name1                                                              |
| parent_id            | None                                                                            |
| project_id           | fc51186c63df417ea63cec6c65a2d564                                                |
| size                 | 0.19                                                                            |
| status               | COMPLETED                                                                       |
| updated              | 2023-11-27T14:18:18                                                             |
+----------------------+---------------------------------------------------------------------------------+
```

#### Check the backup data in Swift

```bash
openstack container list
+------------------+
| Name             |
+------------------+
| my-trove-backups |
+------------------+
openstack object list my-trove-backups
+--------------------------------------------------+
| Name                                             |
+--------------------------------------------------+
| 1ecd0a75-e4aa-400b-b0c8-cb738944fd43.xbstream.gz |
+--------------------------------------------------+
```

#### Restore a database instance

Now assume that the `mysql1` database instance is damaged and it needs to be restored. In this example, you use the openstack database instance create command to create a new database instance called `mysql2`.
- Specify that the new `mysql2` instance has the same flavor (d2) and the same root volume size (1) as the original mysql1 instance.
- Use the `--backup` argument to indicate that this new instance is based on the backup artifact identified by the ID of `mysql-backup-name1`.

```bash
openstack database instance create mysql2 --flavor d2 --nic net-id=$network_id
      --datastore mysql --datastore-version 8.0.29 --datastore-version-number 8.0.29 --size 1 \
      --backup $(openstack database backup show mysql-backup-name1 -f value -c id)
+--------------------------+--------------------------------------+
| Field                    | Value                                |
+--------------------------+--------------------------------------+
| allowed_cidrs            | []                                   |
| created                  | 2022-10-24T01:56:55                  |
| datastore                | mysql                                |
| datastore_version        | 8.0.29                               |
| datastore_version_number | 8.0.29                               |
| encrypted_rpc_messaging  | True                                 |
| flavor                   | d2                                   |
| id                       | 62f0f152-8cd5-42b3-9cd6-91bda651a4c0 |
| name                     | mysql2                               |
| operating_status         |                                      |
| public                   | False                                |
| region                   | RegionOne                            |
| server_id                | None                                 |
| service_status_updated   | 2022-10-24T01:56:55                  |
| status                   | BUILD                                |
| tenant_id                | fc51186c63df417ea63cec6c65a2d564     |
| updated                  | 2022-10-24T01:56:55                  |
| volume                   | 1                                    |
| volume_id                | None                                 |
+--------------------------+--------------------------------------+
```

#### Verify backup

Now check that the new `mysql2` instance has the same characteristics as the original `mysql1` instance.

Get the ID of the new `mysql2` instance.

Use the `openstack database instance show` command to display information about the new `mysql2` instance.

```bash
openstack database instance show mysql2
+--------------------------+-------------------------------------------------------------------------------------------------+
| Field                    | Value                                                                                           |
+--------------------------+-------------------------------------------------------------------------------------------------+
| addresses                | [{'address': '10.0.0.8', 'type': 'private', 'network': '33f3a589-b806-4212-9a59-8e058cac0699'}] |
| allowed_cidrs            | []                                                                                              |
| created                  | 2022-10-24T01:58:51                                                                             |
| datastore                | mysql                                                                                           |
| datastore_version        | 8.0.29                                                                                          |
| datastore_version_number | 8.0.29                                                                                          |
| encrypted_rpc_messaging  | True                                                                                            |
| flavor                   | d2                                                                                              |
| id                       | 6eef378d-1d9c-4e48-b206-b3db130d750d                                                            |
| ip                       | 10.0.0.8                                                                                        |
| name                     | mysql2                                                                                          |
| operating_status         | HEALTHY                                                                                         |
| public                   | False                                                                                           |
| region                   | RegionOne                                                                                       |
| server_id                | 7a8cd089-bd1c-4230-aedd-ced4e945ad46                                                            |
| service_status_updated   | 2022-10-24T02:12:35                                                                             |
| status                   | ACTIVE                                                                                          |
| tenant_id                | fc51186c63df417ea63cec6c65a2d564                                                                |
| updated                  | 2022-10-24T02:05:03                                                                             |
| volume                   | 1                                                                                               |
| volume_id                | 7080954f-e22f-4442-8f40-e26aaa080c9d                                                            |
| volume_used              | 0.19                                                                                            |
+--------------------------+-------------------------------------------------------------------------------------------------+
```

**NOTE:** The data store, flavor ID, and volume size have the same values as in the original `mysql1` instance.

#### Clean up

At this point, you might want to delete the disabled `mysql1` instance, by using the `openstack database instance delete` command.

```bash
openstack database instance delete INSTANCE_ID
```

### Create incremental backups

Incremental backups let you chain together a series of backups. You start with a regular backup. Then, when you want to create a subsequent incremental backup, you specify the parent backup.

Restoring a database instance from an incremental backup is the same as creating a database instance from a regular backup. the Database service handles the process of applying the chain of incremental backups.

Create an incremental backup based on a parent backup:

```bash
openstack database backup create mysql-backup-name1.1 --instance mysql1 --swift-container 'my-trove-backups' \
      --parent $(openstack database backup show mysql-backup-name1 -f value -c id)
+----------------------+--------------------------------------+
| Field                | Value                                |
+----------------------+--------------------------------------+
| created              | 2022-10-24T02:38:41                  |
| datastore            | mysql                                |
| datastore_version    | 8.0.29                               |
| datastore_version_id | 324f2bdf-6099-4754-a5f9-82abee026a19 |
| description          | None                                 |
| id                   | e15ae06a-3afb-4794-8890-7059317b2218 |
| instance_id          | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f |
| locationRef          | None                                 |
| name                 | mysql-backup-name1.1                 |
| parent_id            | 1ecd0a75-e4aa-400b-b0c8-cb738944fd43 |
| project_id           | fc51186c63df417ea63cec6c65a2d564     |
| size                 | None                                 |
| status               | NEW                                  |
| updated              | 2022-10-24T02:38:41                  |
+----------------------+--------------------------------------+
```