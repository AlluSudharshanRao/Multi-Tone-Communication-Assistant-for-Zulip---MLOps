resource "helm_release" "zulip" {
  count = var.deploy_zulip && var.zulip_helm_chart_path != "" ? 1 : 0

  name             = "zulip-${var.project_id_suffix}"
  namespace        = kubernetes_namespace.zulip.metadata[0].name
  create_namespace = false
  chart            = var.zulip_helm_chart_path

  values = [for f in var.zulip_values_files : file(f)]
}
