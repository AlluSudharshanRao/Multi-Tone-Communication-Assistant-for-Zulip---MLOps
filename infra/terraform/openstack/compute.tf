locals {
  control_plane_name = "${var.instance_name}-${var.project_id_suffix}-control-plane"
  worker_name        = "${var.instance_name}-${var.project_id_suffix}-worker"

  control_plane_reservation_id = var.control_plane_blazar_reservation_id != "" ? var.control_plane_blazar_reservation_id : var.blazar_reservation_id
  worker_reservation_id        = var.worker_blazar_reservation_id
}

resource "openstack_compute_instance_v2" "control_plane" {
  name            = local.control_plane_name
  image_name      = var.image_name
  key_pair        = var.key_pair
  security_groups = distinct(concat(var.security_groups, [openstack_networking_secgroup_v2.mlops_cluster.name]))

  flavor_id   = local.control_plane_reservation_id != "" ? local.control_plane_reservation_id : null
  flavor_name = local.control_plane_reservation_id != "" ? null : var.flavor_name

  network {
    uuid = var.network_id
  }

  user_data = var.install_k3s_cloud_init ? templatefile("${path.module}/templates/k3s-cloud-init.yaml.tftpl", {}) : null

  depends_on = [openstack_networking_router_interface_v2.project_subnet]
}

resource "openstack_compute_instance_v2" "worker" {
  name            = local.worker_name
  image_name      = var.image_name
  key_pair        = var.key_pair
  security_groups = distinct(concat(var.security_groups, [openstack_networking_secgroup_v2.mlops_cluster.name]))

  flavor_id   = local.worker_reservation_id != "" ? local.worker_reservation_id : null
  flavor_name = local.worker_reservation_id != "" ? null : var.flavor_name

  network {
    uuid = var.network_id
  }

  depends_on = [openstack_networking_router_interface_v2.project_subnet]
}

data "openstack_networking_port_v2" "control_plane_port" {
  device_id  = openstack_compute_instance_v2.control_plane.id
  network_id = var.network_id

  depends_on = [openstack_compute_instance_v2.control_plane]
}

data "openstack_networking_port_v2" "worker_port" {
  device_id  = openstack_compute_instance_v2.worker.id
  network_id = var.network_id

  depends_on = [openstack_compute_instance_v2.worker]
}

resource "openstack_networking_floatingip_v2" "control_plane_fip" {
  pool = var.floating_ip_pool

  depends_on = [openstack_networking_router_interface_v2.project_subnet]
}

resource "openstack_networking_floatingip_associate_v2" "control_plane_fip_assoc" {
  floating_ip = openstack_networking_floatingip_v2.control_plane_fip.address
  port_id     = data.openstack_networking_port_v2.control_plane_port.id

  depends_on = [
    openstack_networking_router_interface_v2.project_subnet,
    openstack_compute_instance_v2.control_plane,
    openstack_networking_floatingip_v2.control_plane_fip,
    data.openstack_networking_port_v2.control_plane_port,
  ]
}
