# Wire Terraform to an existing cluster (k3s kubeconfig on disk). Apply after openstack + k3s_install.

provider "kubernetes" {
  config_path    = pathexpand(var.kubeconfig_path)
  config_context = var.kube_context != "" ? var.kube_context : null
}

provider "helm" {
  kubernetes {
    config_path    = pathexpand(var.kubeconfig_path)
    config_context = var.kube_context != "" ? var.kube_context : null
  }
}
