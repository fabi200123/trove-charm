## Trove Instalation

### Objectives

This document provides a step-by-step guide for manual installation of Trove with an existing OpenStack environment for development purposes.

This document will not cover OpenStack setup for other services.

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

The Trove database instances are spawned with 2 NICs attached to them, one for the tenant network, and one for the management network. The instances have Trove guest agents running in them, which are supposed to connect to the Trove control plane through AMQP using the management NIC. In a typical Juju OpenStack deployment, they should be able to connect to the same RabbitMQ units as the Trove control plane. In addition to that, the subnet allocated for Trove instances need to sufficiently large enough to allow the maximum number of instances and controllers likely to be deployed throughout the lifespan of the cloud.

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

#### High Level Overview of a Trove Guest Instance

At the most basic level, a Trove Guest Instance is a Nova instance launched by Trove in response to a create command. This section describes the various components of a Trove Guest Instance.

##### Operating System

The officially supported operating system is Ubuntu, based on which the functional tests are running.

##### Trove Guest Agent

The guest agent runs inside the Nova instances that are used to run the database engines. The agent listens to the messaging bus for the topic and is responsible for actually translating and executing the commands that are sent to it by the task manager component for the particular datastore.

Trove guest agent is responsible for datastore docker container management.

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

- Currently, only guest_os=ubuntu and guest_os_release=jammy are fully tested and supported.

- Default input values:

```bash
guest_os=ubuntu
guest_os_release=jammy
dev_mode=true
guest_username=ubuntu
output_image_path=$HOME/images/trove-guest-${guest_os}-${guest_os_release}-dev.qcow2
```

- `dev_mode=true` is mainly for testing purpose for trove developers and it’s necessary to build the image on the trove controller host, because the host and the guest VM need to ssh into each other without password. In this mode, when the trove guest agent code is changed, the image doesn’t need to be rebuilt which is convenient for debugging. Trove guest agent will ssh into the controller node and download trove code during the service initialization.

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

Once the image build is finished, the cloud administrator needs to register the image in Glance and register a new datastore or version in Trove using trove-manage command, e.g. after building an image for MySQL 5.7.29:

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

trove-manage db_load_datastore_config_parameters mysql 5.7.29 ${trove_repo_dir}/trove/templates/mysql/validation-rules.json
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

#### Deploy a database instace

Now, you can deploy database instances:

```bash
openstack database instance create mysql_instance_1 --flavor m1.large --size 3 \
  --nic net-id=$TENANT_NET_UUID --databases test --users userA:Passw0rd \
  --datastore mysql --datastore-version 5.7.29 --is-public \
  --allowed-cidr $TENANT_NET_CIDR
```

To check that the instances become **ACTIVE**, run the following command:

```bash
openstack database instance list
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