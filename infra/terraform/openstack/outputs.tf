output "project_id_suffix" {
  value = var.project_id_suffix
}

output "instance_name" {
  value = openstack_compute_instance_v2.k8s_node.name
}

output "instance_id" {
  value = openstack_compute_instance_v2.k8s_node.id
}

output "floating_ip" {
  value       = openstack_networking_floatingip_v2.fip.address
  description = "SSH here; retrieve kubeconfig from the node after k3s/kube setup"
}

output "ansible_inventory_ini" {
  description = "Convenience output for Ansible inventory (INI format)."
  value = <<-EOT
  [chameleon]
  ${openstack_networking_floatingip_v2.fip.address}

  [chameleon:vars]
  ansible_user=cc
  EOT
}
