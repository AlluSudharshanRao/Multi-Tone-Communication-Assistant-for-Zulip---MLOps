locals {
  vm_name = "${var.instance_name}-${var.project_id_suffix}"
}

resource "openstack_compute_instance_v2" "k8s_node" {
  name            = local.vm_name
  image_name      = var.image_name
  key_pair        = var.key_pair
  security_groups = var.security_groups

  # Chameleon Blazar: an *instance reservation* is exposed as its own flavor
  # (Horizon shows "Flavor Name: reservation:<uuid>", Flavor ID == reservation UUID).
  # Use flavor_id = reservation id — do NOT also pass m1.* + scheduler hint.
  flavor_id   = var.blazar_reservation_id != "" ? var.blazar_reservation_id : null
  flavor_name = var.blazar_reservation_id != "" ? null : var.flavor_name

  network {
    uuid = var.network_id
  }

  user_data = var.install_k3s_cloud_init ? templatefile("${path.module}/templates/k3s-cloud-init.yaml.tftpl", {}) : null

  # depends_on must be static (no conditional). When create_public_router is false, count=0 and this is a no-op.
  depends_on = [openstack_networking_router_interface_v2.project_subnet]
}

data "openstack_networking_port_v2" "k8s_node_port" {
  # The compute_instance_v2 resource doesn't always populate network[0].port.
  # Query Neutron for the port attached to this server on our tenant network.
  device_id  = openstack_compute_instance_v2.k8s_node.id
  network_id = var.network_id

  depends_on = [openstack_compute_instance_v2.k8s_node]
}

resource "openstack_networking_floatingip_v2" "fip" {
  pool = var.floating_ip_pool

  depends_on = [openstack_networking_router_interface_v2.project_subnet]
}

# Neutron association (compute associate API is deprecated; same routing rules apply).
resource "openstack_networking_floatingip_associate_v2" "fip_assoc" {
  # Provider expects the floating IP *address*, not the resource ID.
  floating_ip = openstack_networking_floatingip_v2.fip.address
  port_id     = data.openstack_networking_port_v2.k8s_node_port.id

  depends_on = [
    openstack_networking_router_interface_v2.project_subnet,
    openstack_compute_instance_v2.k8s_node,
    openstack_networking_floatingip_v2.fip,
    data.openstack_networking_port_v2.k8s_node_port,
  ]
}
